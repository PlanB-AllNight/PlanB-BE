import pandas as pd
import os
from sqlmodel import Session, select
from backend.models.budget import CategoryBudget
from backend.models.spending import SpendingAnalysis, SpendingCategoryStats
from analyze_spending import CATEGORY_MAP

DATA_PATH = os.path.join(os.path.dirname(__file__), "../data/mydata.json")

# 카테고리 성격 분류 (needs / wants / savings)
CAT_TYPE = {
    # Needs (필수)
    "주거": "needs", 
    "통신/구독": "needs", 
    "교통": "needs", 
    "식사": "needs", 
    "특별지출": "needs",

    # Wants (선택)
    "카페/디저트": "wants", 
    "사회/모임": "wants", 
    "쇼핑/꾸미기": "wants",
    "취미/여가": "wants", 
    "데이트": "wants", 
    "교육/학습": "wants", 

    # Savings (저축)
    "저축/투자": "savings" 
}

# 카테고리별 성격
CATEGORY_TYPE_MAP = {
    "주거": "FIXED", "통신/구독": "FIXED_OR_SUBSCRIPTION", "특별지출": "FIXED",
    "교통": "SEMI_FIXED", "교육/학습": "SEMI_FIXED",
    "식사": "VARIABLE_ESSENTIAL", # 줄일 수 있지만 밥은 먹어야 함
    "카페/디저트": "VARIABLE_HABIT", # 습관성 지출
    "술집": "VARIABLE_SOCIAL", # 사회생활
    "쇼핑/꾸미기": "VARIABLE_LUXURY", # 사치성
    "취미/여가": "VARIABLE_LUXURY"
}

# 카테고리 타입별 가이드
TYPE_GUIDE = {
    "FIXED": "고정 지출 (월세, 공과금 등). 절대 줄이지 말고 지난달 금액 그대로 유지해.",
    "FIXED_OR_SUBSCRIPTION": "고정비지만 '구독(OTT, 음원)'이 섞여 있음. 필수 통신비는 유지하되, 넷플릭스 같은 구독은 해지를 권유해.",
    "SEMI_FIXED": "준고정 지출 (교통, 교육). 꼭 필요하지만 택시비 같은 낭비가 보이면 줄이라고 제안해.",
    "VARIABLE_ESSENTIAL": "필수 변동 지출 (식사). 굶을 순 없으니 무리하게 깎지 말고, 배달/외식만 줄이는 방향으로 현실적인 금액을 잡아.",
    "VARIABLE_HABIT": "습관성 지출 (카페, 편의점). '횟수'를 줄이는 게 핵심이야. 과감하게 예산을 삭감해.",
    "VARIABLE_SOCIAL": "사회생활 (술자리, 모임). 0원으로 만들지 말고, 월 1~2회 정도로 빈도를 제한해.",
    "VARIABLE_LUXURY": "사치성 지출 (쇼핑, 취미). 예산이 부족하면 가장 먼저, 가장 많이 깎아야 할 1순위 항목이야."
}

# 예산 규칙
RULES = {
    "50/30/20": {"needs": 0.5, "wants": 0.3, "savings": 0.2},
    "60/20/20": {"needs": 0.6, "wants": 0.2, "savings": 0.2},
    "40/30/30": {"needs": 0.4, "wants": 0.3, "savings": 0.3},
}

def recommend_budget_logic(
        user_id: int,
        selected_plan: str,
        recent_analysis: SpendingAnalysis,
        session: Session
):

    target_month = recent_analysis.month
    total_income = recent_analysis.total_income

    # 상세 데이터 로드 (AI 분석용)
    spending_history = []
    current_spending_map = {}   # 계산용 (카테고리: 금액)

    # 상세 데이터 로드 시도
    try:
        # 파일 존재 확인
        if not os.path.exists(DATA_PATH):
            raise FileNotFoundError("데이터 파일이 없습니다.")
        
        try:
            df = pd.read_json(DATA_PATH)
        except ValueError:
            raise ValueError("JSON 파일 형식이 올바르지 않습니다.")
        
        df['dt'] = pd.to_datetime(df['date'])
        current_df = df[df['dt'].dt.strftime('%Y-%m') == target_month].copy()

        # 데이터 존재 여부 체크
        if current_df.empty:
            raise ValueError(f"{target_month} 데이터가 없습니다.")
        
        # 카테고리 매핑 (Raw -> Standard)
        current_df['std_category'] = current_df['category'].map(CATEGORY_MAP).fillna("기타")
        expense_df = current_df[current_df['type'] == '출금']

        # 카테고리별 상세 내역 가공 (낭비 탐지용 데이터)
        for cat in expense_df['std_category'].unique():
            cat_df = expense_df[expense_df['std_category'] == cat]
            amount = int(cat_df['amount'].sum())

            current_spending_map[cat] = amount

            # 금액, 횟수, 평균단가 모두 계산
            store_stats = cat_df.groupby('store')['amount'].agg(['sum', 'count', 'mean'])

            # 정렬 기준 1: 돈을 많이 쓴 곳 - 상위 3개
            top_sum_stores = store_stats.sort_values('sum', ascending=False).head(3)
            # 정렬 기준 2: 너무 자주 간 곳 - 5회 이상 방문한 곳 중 상위 2개
            habit_stores = store_stats[store_stats['count'] >= 5].sort_values('count', ascending=False).head(2)

            combined_stores = pd.concat([top_sum_stores, habit_stores])
            combined_stores = combined_stores[~combined_stores.index.duplicated(keep='first')]

            # 포맷: "상점명(횟수/총액/1회평균)"
            details_list = []
            for store, row in combined_stores.iterrows():
                avg_price = int(row['mean'])
                details_list.append(f"{store}({int(row['count'])}회/{int(row['sum']):,}원/평균{avg_price:,}원)")
            
            details_str = ", ".join(details_list)
            
            spending_history.append({
                "category": cat,
                "amount": amount,
                "type": CAT_TYPE.get(cat, "wants"),
                "details": details_str
            })
        
    except Exception as e:
        print(f"상세 데이터 로드 실패: {e}")

        # DB에 저장된 통계 데이터 로드 (SpendingCategoryStats)
        stats = session.exec(
            select(SpendingCategoryStats)
            .where(SpendingCategoryStats.analysis_id == recent_analysis.id)
        ).all()

        if stats:
            for stat in stats:
                cat = stat.category_name
                amount = stat.amount
                current_spending_map[cat] = amount

                spending_history.append({
                    "category": cat, "amount": amount,
                    "type": CAT_TYPE.get(cat, "wants"),
                    "details": f"총 {stat.count}회 결제"
                })
        else:
            print("DB에도 데이터가 없습니다.")

    # 룰에 따른 예산 총액 계산
    ratios = RULES.get(selected_plan, RULES["40/30/30"])
    budget_caps = {
        "needs": int(total_income * ratios["needs"]),
        "wants": int(total_income * ratios["wants"]),
        "savings": int(total_income * ratios["savings"])
    }

    # 상세 예산 배분
    details = {"needs": [], "wants": [], "savings": []}
    
    total_wants_curr = sum(current_spending_map.get(k, 0) for k, v in CAT_TYPE.items() if v == "wants")
    if total_wants_curr == 0: total_wants_curr = 1

    for cat, type_ in CAT_TYPE.items():
        curr = current_spending_map.get(cat, 0)
        rec_amt = 0
        status = "적정"
        
        if type_ == "needs":
            if curr > 0:
                # 고정비 성격(주거, 통신)은 유지, 나머지는 90%
                rec_amt = curr if cat in ["주거", "통신/구독"] else int(curr * 0.9)
            else:
                rec_amt = 0
        elif type_ == "wants":
            if curr > 0:
                # 비례 배분: (내 지출 / 전체 wants 지출) * wants 예산 한도
                rec_amt = int((curr / total_wants_curr) * budget_caps["wants"])
            else:
                rec_amt = 0
        elif type_ == "savings":
            rec_amt = budget_caps["savings"]  # 저축은 목표치 강제

        rec_amt = round(rec_amt, -3)

        if curr > rec_amt * 1.1: status = "과소비"
        elif curr < rec_amt * 0.9: status = "여유"
        
        details[type_].append(CategoryBudget(
            category=cat, current=curr, budget=rec_amt, status=status
        ))
    
    return {
        "total_income": total_income,
        "selected_plan": selected_plan,
        "summary": {
            "needs": {"amount": budget_caps["needs"], "percent": int(ratios["needs"]*100)},
            "wants": {"amount": budget_caps["wants"], "percent": int(ratios["wants"]*100)},
            "savings": {"amount": budget_caps["savings"], "percent": int(ratios["savings"]*100)}
        },
        "spending_history": spending_history,
        "spending_history_map": current_spending_map
    }