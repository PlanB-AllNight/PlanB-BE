import json
import pandas as pd
import os
from datetime import datetime
import calendar
from typing import Dict, List, Any, Optional

# 데이터 경로
DATA_PATH = os.path.join(os.path.dirname(__file__), "../data/mydata.json")

# 카테고리 매핑
CATEGORY_MAP = {
    "식비": "식사", "편의점": "식사",
    "카페": "카페/디저트",
    "사회": "사회/모임", "술집": "사회/모임", "회식": "사회/모임",
    "쇼핑": "쇼핑/꾸미기", "패션": "쇼핑/꾸미기", "뷰티": "쇼핑/꾸미기",
    "도서": "교육/학습", "학습": "교육/학습", "학원": "교육/학습",
    "여가": "취미/여가",
    "교통": "교통", "택시": "교통",
    "주거": "주거", "월세": "주거",
    "구독": "통신/구독", "통신": "통신/구독",
    "저축": "저축/투자", "투자": "저축/투자",
    "수입": "수입"
}

# 과소비 기준
OVERSPEND_THRESHOLDS = {
    "카페/디저트": 0.15,
    "사회/모임": 0.20,
    "쇼핑/꾸미기": 0.20,
    "식사": 0.40,
}

# 데모 날짜 (테스트용)
DEMO_DATE = datetime(2024, 10, 25)


def analyze_spending(
    month: Optional[str] = None,
    reference_date: Optional[str] = None,
    use_demo_mode: bool = True  # 기본값: 데모 모드
) -> Dict[str, Any]:
    
    try:
        if not os.path.exists(DATA_PATH):
            return {"error": "데이터 파일을 찾을 수 없습니다."}
        
        df = pd.read_json(DATA_PATH)
        df['date'] = pd.to_datetime(df['date'])
        
        if use_demo_mode:
            now = DEMO_DATE
        elif reference_date:
            try:
                now = datetime.strptime(reference_date, "%Y-%m-%d")
            except ValueError:
                return {"error": "reference_date 형식 오류 (yyyy-mm-dd)"}
        else:
            # 실제 배포: mydata의 최신 날짜 사용
            dates = df['date'].tolist()
            now = max(dates) if dates else datetime.now()
        
        current_year = now.year
        current_month = now.month
        current_day = now.day
        
        target_year = current_year
        target_month = current_month
        
        if month:
            if "월" in month:
                nums = [int(s) for s in month.replace("월", "") if s.isdigit()]
                if nums:
                    target_month = int(''.join(map(str, nums)))
            elif "-" in month:
                parts = month.split("-")
                if len(parts) == 2:
                    target_year = int(parts[0])
                    target_month = int(parts[1])
        
        df = df[(df['date'].dt.year == target_year) & (df['date'].dt.month == target_month)]
        
        if df.empty:
            return {
                "error": f"{target_year}년 {target_month}월 데이터가 없습니다.",
                "suggestion": "다른 월을 선택하거나 데이터를 업로드해주세요."
            }
        
        df['display_category'] = df['category'].map(CATEGORY_MAP).fillna("기타")
        
        # 수입/지출/저축 분리
        income_df = df[df['type'] == '입금']
        expense_df = df[df['type'] == '출금']
        
        # 저축/투자는 소비 통계에서 제외 (자산 이동)
        spending_df = expense_df[expense_df['display_category'] != '저축/투자']
        saving_df = expense_df[expense_df['display_category'] == '저축/투자']
        
        total_income = int(income_df['amount'].sum())
        total_spent = int(spending_df['amount'].sum())  # 순수 소비
        total_saved = int(saving_df['amount'].sum())    # 저축액
        
        # 저축 가능액 = 수입 - 순수 소비 (저축 제외한 여유)
        save_potential = total_income - total_spent
        
        # 예상 지출액 계산
        is_current_month = (target_year == current_year and target_month == current_month)
        daily_average = 0
        projected_total = total_spent
        days_passed = 0
        days_remaining = 0
        
        if is_current_month and total_spent > 0:
            _, last_day = calendar.monthrange(target_year, target_month)
            days_passed = current_day
            days_remaining = max(0, last_day - current_day)
            
            if days_passed > 0:
                daily_average = int(total_spent / days_passed)
                projected_total = total_spent + (daily_average * days_remaining)
        
        # 카테고리별 집계
        cat_group = spending_df.groupby('display_category')['amount'].agg(['sum', 'count'])
        
        if total_spent > 0:
            cat_group['percent'] = (cat_group['sum'] / total_spent * 100).round(1)
        else:
            cat_group['percent'] = 0.0
        
        cat_group = cat_group.sort_values(by='sum', ascending=False)
        
        top_category = cat_group.index[0] if not cat_group.empty else "없음"
        
        # 과소비 탐지 및 인사이트 생성
        overspent_category = None
        insights = []
        suggestions = []
        
        if is_current_month and projected_total > total_spent * 1.15:
            insights.append({
                "type": "alert",
                "category": "전체",
                "message": f"현재 소비 속도라면 월말 약 {projected_total:,}원 지출 예상",
                "detail": f"일평균 {daily_average:,}원 (남은 {days_remaining}일)"
            })
        
        for cat_name, threshold in OVERSPEND_THRESHOLDS.items():
            if cat_name in cat_group.index:
                pct = cat_group.loc[cat_name, 'percent']
                amt = int(cat_group.loc[cat_name, 'sum'])
                cnt = int(cat_group.loc[cat_name, 'count'])
                
                if pct > (threshold * 100):
                    if not overspent_category:
                        overspent_category = cat_name
                    
                    insights.append({
                        "type": "warning",
                        "category": cat_name,
                        "message": f"'{cat_name}' 지출 비중({pct}%)이 권장({int(threshold*100)}%)보다 높습니다.",
                        "detail": f"{cnt}회 사용, 총 {amt:,}원"
                    })
                    
                    save_amt = int(amt * 0.1)
                    suggestions.append({
                        "category": cat_name,
                        "action": f"{cat_name} 지출을 10% 줄이기",
                        "expected_saving": save_amt,
                        "message": f"월 {save_amt:,}원 절약 가능"
                    })
        
        if total_saved > 0:
            saving_count = len(saving_df)
            insights.append({
                "type": "positive",
                "category": "저축/투자",
                "message": f"이번 달 {saving_count}회 저축 실행",
                "detail": f"총 {total_saved:,}원 저축 👏"
            })
        
        if top_category != "없음":
            top_pct = cat_group.loc[top_category, 'percent']
            insights.append({
                "type": "info",
                "category": top_category,
                "message": f"총 소비의 {top_pct}%가 '{top_category}'에서 발생",
                "detail": f"주요 지출 항목입니다"
            })
        
        insight_summary = f"{target_month}월 소비는 {top_category} 위주이며, 예상 소비액은 {projected_total:,}원입니다."
        
        chart_data = []
        for cat_name, row in cat_group.iterrows():
            chart_data.append({
                "category_name": cat_name,
                "amount": int(row['sum']),
                "count": int(row['count']),
                "percent": float(row['percent'])
            })
        
        return {
            # SpendingAnalysis
            "month": f"{target_year}-{target_month:02d}",
            "analysis_date": now.strftime("%Y-%m-%d"),
            "total_income": total_income,
            "total_spent": total_spent,
            "total_saved": total_saved,
            "save_potential": save_potential,
            "daily_average": daily_average,
            "projected_total": projected_total,
            
            "top_category": top_category,
            "overspent_category": overspent_category if overspent_category else "양호",
            
            "insight_summary": insight_summary,
            "insights": insights,
            "suggestions": suggestions,
            
            # SpendingCategoryStats
            "chart_data": chart_data,
            
            # 메타 정보
            "meta": {
                "is_current_month": is_current_month,
                "days_passed": days_passed,
                "days_remaining": days_remaining
            }
        }
    
    except Exception as e:
        return {"error": f"분석 중 오류 발생: {str(e)}"}


# 테스트용 함수 (기존 함수명 호환)
def analyze_spending_logic(month: str = None):
    """
    기존 코드 호환용 래퍼 함수
    """
    result = analyze_spending(month=month, use_demo_mode=True)
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    print("=" * 60)
    print("Tool 1 최종 테스트 (10월 25일 기준)")
    print("=" * 60)
    
    result = analyze_spending(month="10월", use_demo_mode=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 60)
    print("DB 저장용 필드 확인")
    print("=" * 60)
    print(f"month: {result['month']}")
    print(f"analysis_date: {result['analysis_date']}")
    print(f"insights 타입: {type(result['insights'])}")
    print(f"suggestions 타입: {type(result['suggestions'])}")
    print(f"chart_data 개수: {len(result['chart_data'])}")