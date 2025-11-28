import pandas as pd
import os
from sqlmodel import Session, select
from typing import Dict, List, Any

from backend.models.analyze_spending import SpendingAnalysis, SpendingCategoryStats
from backend.tools.analyze_spending import CATEGORY_MAP


DATA_PATH = os.path.join(os.path.dirname(__file__), "../data/mydata.json")

# 카테고리 타입 정의
CAT_TYPE = {
    # Needs
    "주거": "needs",
    "통신/구독": "needs",
    "교통": "needs",
    "식사": "needs",
    "특별지출": "needs",

    # Wants
    "카페/디저트": "wants",
    "사회/모임": "wants",
    "쇼핑/꾸미기": "wants",
    "취미/여가": "wants",
    "데이트": "wants",
    "교육/학습": "wants",

    # Savings
    "저축/투자": "savings",
}

# 기본 예산 룰
RULES = {
    "50/30/20": {"needs": 0.5, "wants": 0.3, "savings": 0.2},
    "60/20/20": {"needs": 0.6, "wants": 0.2, "savings": 0.2},
    "40/30/30": {"needs": 0.4, "wants": 0.3, "savings": 0.3},
}

BUFFER_THRESHOLD = 100_000


# -------------------------------------------------------------
# 공통 유틸
# -------------------------------------------------------------
def sum_group(items: List[Dict[str, Any]]) -> int:
    return sum(int(it["recommended_amount"]) for it in items)


def ensure_savings_exists(base_items: List[Dict[str, Any]]):
    """저축/투자가 존재하지 않을 경우 항목 추가"""
    if not any(it["type"] == "savings" for it in base_items):
        base_items.append(
            {
                "category": "저축/투자",
                "recommended_amount": 0,
                "curr_amount": 0,
                "type": "savings",
            }
        )


def build_base_items(spending_history, category_type_map):
    """지난달 소비 기록 → Base item 구조로 변환"""
    spending_map = {}

    for item in spending_history:
        cat = item["category"]
        amt = int(item.get("amount", 0) or 0)
        spending_map[cat] = spending_map.get(cat, 0) + amt

    # 모든 카테고리를 0원으로라도 포함
    for cat in category_type_map.keys():
        spending_map.setdefault(cat, 0)

    base_items = [
        {
            "category": cat,
            "recommended_amount": amt,
            "curr_amount": amt,
            "type": category_type_map[cat],
        }
        for cat, amt in spending_map.items()
    ]

    ensure_savings_exists(base_items)
    return base_items


# -------------------------------------------------------------
# Needs 조정 로직
# -------------------------------------------------------------
def lower_bound_needs(curr):
    """Needs 최소 보장값: 지난달의 80%"""
    return int(curr * 0.8)


def adjust_needs(fixed_needs, adjustable_needs, needs_cap):
    """Needs 감액 및 여유분 분배 전체 수행"""
    meal = [x for x in adjustable_needs if x["category"] == "식사"]
    transport = [x for x in adjustable_needs if x["category"] == "교통"]
    other = [x for x in adjustable_needs if x["category"] not in ["식사", "교통"]]

    priorities = [other, transport, meal]

    sum_needs = sum_group(fixed_needs) + sum_group(adjustable_needs)

    needs_adjustment_info = {
        "is_over_cap": False,
        "over_amount": 0,
        "hard_to_adjust": False,
        "reasons": [],
        "adjustable_amount": 0,
    }

    # ------- CAP 초과 시 감액 -------
    if sum_needs > needs_cap:
        exceed = sum_needs - needs_cap

        # 감액량 계산
        for it in other + transport + meal:
            curr = it["curr_amount"]
            min_val = lower_bound_needs(curr)
            reducible = max(it["recommended_amount"] - min_val, 0)

            needs_adjustment_info["reasons"].append({
                "category": it["category"],
                "curr": curr,
                "min_val": min_val,
                "possible_reduce": reducible,
            })

            needs_adjustment_info["adjustable_amount"] += reducible

        # 감액 적용
        for group in priorities:
            for it in group:
                if exceed <= 0:
                    break

                curr = it["curr_amount"]
                min_val = lower_bound_needs(curr)

                reducible = it["recommended_amount"] - min_val
                if reducible <= 0:
                    continue

                delta = min(exceed, reducible)
                it["recommended_amount"] -= delta
                exceed -= delta

        if exceed > 0:
            needs_adjustment_info["is_over_cap"] = True
            needs_adjustment_info["over_amount"] = exceed
            needs_adjustment_info["hard_to_adjust"] = True

    # ------- CAP 이하 시 여유분 분배 -------
    final_sum = sum_group(fixed_needs) + sum_group(adjustable_needs)
    remain = max(needs_cap - final_sum, 0)

    def add_extra(group, weight, remaining, total_w):
        """실제 추가된 금액을 정확히 추적하여 반환"""
        if not group:
            return remaining

        share = remaining * weight // total_w
        if share <= 0:
            return remaining

        per_item = share // len(group)
        if per_item <= 0:
            return remaining

        actually_added = 0  # 실제 추가된 금액 추적
        for it in group:
            curr = it["curr_amount"]
            max_allow = int(curr * 1.3) if curr > 0 else it["recommended_amount"] + per_item
            
            before = it["recommended_amount"]
            it["recommended_amount"] = min(it["recommended_amount"] + per_item, max_allow)
            actually_added += (it["recommended_amount"] - before)  # 실제 추가량 누적

        return remaining - actually_added  # 실제 추가된 금액만큼만 차감

    needs_buffer = 0
    if remain > 0:
        distribute_amount = min(remain, BUFFER_THRESHOLD)
        total_weight = 3 * len(meal) + 2 * len(transport) + 1 * len(other)

        if total_weight > 0:
            distribute_amount = min(distribute_amount, remain)
            remaining = distribute_amount
            remaining = add_extra(meal, 3, remaining, total_weight)
            remaining = add_extra(transport, 2, remaining, total_weight)
            remaining = add_extra(other, 1, remaining, total_weight)

            remain -= (distribute_amount - remaining)  # 실제 사용된 금액만 차감

        needs_buffer = remain

    return needs_adjustment_info, needs_buffer


# -------------------------------------------------------------
# Wants 조정 로직
# -------------------------------------------------------------
def compute_min_wants(cat, curr):
    """Wants 최소보장 로직"""
    if curr <= 0:
        return 0

    return {
        "카페/디저트": int(curr * 0.4),
        "쇼핑/꾸미기": int(curr * 0.3),
        "취미/여가": int(curr * 0.3),
        "교육/학습": int(curr * 0.5),
        "사회/모임": int(curr * 0.4),
        "데이트": int(curr * 0.4),
    }.get(cat, int(curr * 0.3))


def adjust_wants(wants_items, wants_cap):
    priorities = [
        "쇼핑/꾸미기",
        "취미/여가",
        "카페/디저트",
        "사회/모임",
        "데이트",
        "교육/학습",
    ]

    def priority_key(item):
        cat = item["category"]
        return priorities.index(cat) if cat in priorities else len(priorities)

    sum_wants = sum_group(wants_items)

    # -------- 감액 --------
    if sum_wants > wants_cap:
        exceed = sum_wants - wants_cap
        total_curr = sum(it["curr_amount"] for it in wants_items) or 1

        # 1차 감액
        for it in sorted(wants_items, key=priority_key):
            if exceed <= 0:
                break

            curr = it["curr_amount"]
            before = it["recommended_amount"]
            min_val = compute_min_wants(it["category"], curr)

            reducible = before - min_val
            if reducible <= 0:
                continue

            ratio = curr / total_curr
            target_reduce = int(exceed * ratio)

            delta = min(target_reduce, reducible, exceed)
            it["recommended_amount"] -= delta
            exceed -= delta

        # 2차 강제 보정
        if exceed > 0:
            for it in sorted(wants_items, key=priority_key):
                if exceed <= 0:
                    break

                curr = it["curr_amount"]
                min_val = compute_min_wants(it["category"], curr)
                reducible = it["recommended_amount"] - min_val
                if reducible <= 0:
                    continue

                delta = min(exceed, reducible)
                it["recommended_amount"] -= delta
                exceed -= delta

    # -------- 여유분 --------
    final_sum = sum_group(wants_items)
    remain = max(wants_cap - final_sum, 0)

    buffer_amount = 0

    if remain > 0:
        extra = min(remain, BUFFER_THRESHOLD)
        remain -= extra

        total_curr = sum(it["curr_amount"] for it in wants_items) or 1
        for it in sorted(wants_items, key=lambda x: x["curr_amount"], reverse=True):
            if extra <= 0:
                break

            curr = it["curr_amount"]
            ratio = curr / total_curr
            add_amt = int(extra * ratio)
            if add_amt <= 0:
                continue

            it["recommended_amount"] += add_amt
            extra -= add_amt

        buffer_amount = remain

    return buffer_amount


# -------------------------------------------------------------
# Savings 조정
# -------------------------------------------------------------
def adjust_savings(savings_items, savings_cap):
    return [{"category": "저축/투자", "recommended_amount": savings_cap}]


# -------------------------------------------------------------
# 메인: Rule 기반 예산 생성
# -------------------------------------------------------------
def compute_rule_based_budget(spending_history, budget_caps, category_type_map):

    needs_cap = budget_caps["needs"]
    wants_cap = budget_caps["wants"]
    savings_cap = budget_caps["savings"]

    # base_item 구성
    base_items = build_base_items(spending_history, category_type_map)

    # 그룹 분류
    needs_items = [x for x in base_items if x["type"] == "needs"]
    wants_items = [x for x in base_items if x["type"] == "wants"]
    savings_items = [x for x in base_items if x["type"] == "savings"]

    # Needs: 고정 vs 조정
    fixed_needs = [it for it in needs_items if it["category"] in ["주거", "통신/구독"]]
    adjustable_needs = [it for it in needs_items if it not in fixed_needs]

    needs_adjustment_info, needs_buffer = adjust_needs(fixed_needs, adjustable_needs, needs_cap)

    # Wants 조정
    wants_buffer = adjust_wants(wants_items, wants_cap)

    # Savings 고정
    savings_result = adjust_savings(savings_items, savings_cap)

    # 최종 결과
    needs_result = [
        {"category": it["category"], "recommended_amount": it["recommended_amount"]}
        for it in (fixed_needs + adjustable_needs)
    ]
    if needs_buffer > 0:
        needs_result.append({"category": "예비비(필수 지출)", "recommended_amount": needs_buffer})

    wants_result = [
        {"category": it["category"], "recommended_amount": it["recommended_amount"]}
        for it in wants_items
    ]
    if wants_buffer > 0:
        wants_result.append({"category": "예비비(선택 지출)", "recommended_amount": wants_buffer})

    return {
        "needs": needs_result,
        "wants": wants_result,
        "savings": savings_result,
        "needs_adjustment_info": {"needs": needs_adjustment_info},
    }


def evaluate_spending_status(current, recommended):
    """
    current(지난달 소비) vs recommended(추천 예산)를 비교해
    '적정', '여유', '과소비' 상태를 반환.
    """
    if recommended <= 0:
        return "적정"  # 추천 0원인 경우는 특별하게 처리 가능

    ratio = current / recommended

    if ratio > 1.1:
        return "과소비"
    elif ratio < 0.9:
        return "여유"
    else:
        return "적정"


def convert_to_comparison_format(recommended_budget, current_spending_map):
    def convert_group(group):
        result = []
        for item in group:
            category = item["category"]
            rec_amount = item["recommended_amount"]
            analyzed_amount = current_spending_map.get(category, 0)
            status = evaluate_spending_status(analyzed_amount, rec_amount)

            result.append({
                "category": category,
                "analyzed_amount": analyzed_amount,
                "recommended_amount": rec_amount,
                "status": status,
            })
        return result

    return {
        "needs": convert_group(recommended_budget["needs"]),
        "wants": convert_group(recommended_budget["wants"]),
        "savings": convert_group(recommended_budget["savings"]),
    }

# -------------------------------------------------------------
# recommend_budget_logic
# -------------------------------------------------------------
def recommend_budget_logic(user_id, selected_plan, recent_analysis, session):

    target_month = recent_analysis.month
    total_income = recent_analysis.total_income

        # 상세 데이터 로드 (AI 분석용)
    spending_history = []
    current_spending_map = {}   # 계산용 (카테고리: 금액)

    try:
        # 파일 존재 확인
        if not os.path.exists(DATA_PATH):
            raise FileNotFoundError("데이터 파일이 없습니다.")

        # JSON 로드
        try:
            df = pd.read_json(DATA_PATH)
        except ValueError:
            raise ValueError("JSON 파일 형식이 올바르지 않습니다.")

        df['dt'] = pd.to_datetime(df['date'])
        current_df = df[df['dt'].dt.strftime('%Y-%m') == target_month].copy()

        if current_df.empty:
            raise ValueError(f"{target_month} 데이터가 없습니다.")

        # 카테고리 매핑
        current_df['std_category'] = current_df['category'].map(CATEGORY_MAP).fillna("기타")
        expense_df = current_df[current_df['type'] == '출금']

        # 상세 소비 분석
        for cat in expense_df['std_category'].unique():
            cat_df = expense_df[expense_df['std_category'] == cat]
            amount = int(cat_df['amount'].sum())

            current_spending_map[cat] = amount

            # 금액·횟수·평균단가
            store_stats = cat_df.groupby('store')['amount'].agg(['sum', 'count', 'mean'])

            # 많이 쓴 상점 상위 3개
            top_sum_stores = store_stats.sort_values('sum', ascending=False).head(3)

            # 자주 간 상점 (5회 이상)
            habit_stores = store_stats[store_stats['count'] >= 5].sort_values('count', ascending=False).head(2)

            combined_stores = pd.concat([top_sum_stores, habit_stores])
            combined_stores = combined_stores[~combined_stores.index.duplicated(keep='first')]

            details = []
            for store, row in combined_stores.iterrows():
                details.append(
                    f"{store}({int(row['count'])}회/"
                    f"{int(row['sum']):,}원/"
                    f"평균{int(row['mean']):,}원)"
                )

            spending_history.append({
                "category": cat,
                "amount": amount,
                "type": CAT_TYPE.get(cat, "wants"),
                "details": ", ".join(details) if details else "주요 소비 패턴 없음"
            })

        # 누락된 카테고리는 0원 처리
        for cat, type_ in CAT_TYPE.items():
            if cat not in current_spending_map:
                current_spending_map[cat] = 0
                spending_history.append({
                    "category": cat,
                    "amount": 0,
                    "type": type_,
                    "details": "총 0회 결제"
                })

    except Exception as e:
        print(f"[파일 로드 실패 → DB fallback] {e}")

        stats = session.exec(
            select(SpendingCategoryStats)
            .where(SpendingCategoryStats.analysis_id == recent_analysis.id)
        ).all()

        if stats:
            for st in stats:
                current_spending_map[st.category_name] = st.amount
                spending_history.append({
                    "category": st.category_name,
                    "amount": int(st.amount),
                    "type": CAT_TYPE.get(st.category_name, "wants"),
                    "details": f"총 {st.count}회 결제"
                })
        else:
            print("DB에서도 데이터 없음")

        # 누락된 카테고리는 0원 처리
        for cat, type_ in CAT_TYPE.items():
            if cat not in current_spending_map:
                current_spending_map[cat] = 0
                spending_history.append({
                    "category": cat,
                    "amount": 0,
                    "type": type_,
                    "details": "총 0회 결제"
                })

    # CAP 계산
    ratios = RULES.get(selected_plan, RULES["50/30/20"])
    budget_caps = {
        "needs": int(total_income * ratios["needs"]),
        "wants": int(total_income * ratios["wants"]),
        "savings": int(total_income * ratios["savings"]),
    }

    # RULE 예산 계산
    recommended = compute_rule_based_budget(
        spending_history=spending_history,
        budget_caps=budget_caps,
        category_type_map=CAT_TYPE,
    )

    converted_budget = convert_to_comparison_format(
        recommended_budget=recommended,
        current_spending_map=current_spending_map
    )

    return {
        "total_income": total_income,
        "selected_plan": selected_plan,
        "summary": {
            "needs": {"amount": budget_caps["needs"], "percent": int(ratios["needs"] * 100)},
            "wants": {"amount": budget_caps["wants"], "percent": int(ratios["wants"] * 100)},
            "savings": {"amount": budget_caps["savings"], "percent": int(ratios["savings"] * 100)},
        },
        "spending_history": spending_history,
        "spending_history_map": current_spending_map,
        "recommended_budget": converted_budget,
        "needs_adjustment_info": recommended.get("needs_adjustment_info", {}),
    }

# =========================================================================================
# 간단 로컬 테스트용 엔트리포인트
# =========================================================================================
if __name__ == "__main__":
    from types import SimpleNamespace
    from pprint import pprint

    # 1) mydata.json 안에 실제로 존재하는 year-month로 맞춰줘야 함
    #    예: 2025-11, 2025-10 등
    TARGET_MONTH = "2024-10"  

    # 2) 테스트용 recent_analysis 흉내 (SpendingAnalysis 대신 duck-typing)
    recent_analysis = SimpleNamespace(
        month=TARGET_MONTH,
        total_income=1_200_000,  
        id=1,
    )

    # 3) 세션은 파일이 잘 읽히면 안 쓰이므로 None으로 넣어도 됨
    dummy_session: Session | None = None

    # 4) 예산안 계산 실행
    result = recommend_budget_logic(
        user_id=1,
        selected_plan="40/30/30",  # 50/30/20, 60/20/20, 40/30/30 중 선택
        recent_analysis=recent_analysis,
        session=dummy_session,
    )

    print("\n===== [요약 summary] =====")
    pprint(result["summary"])

    print("\n===== [지난달 소비 내역 요약] =====")
    for item in result["spending_history"]:
        print(
            f"- {item['category']}: {item['amount']:,}원 "
            f"({item['type']}) / {item['details']}"
        )

    print("\n===== [룰 기반 예산안: Needs] =====")
    for it in result["recommended_budget"]["needs"]:
        print(f"  {it['category']}: {it['recommended_amount']:,}원")

    print("\n===== [룰 기반 예산안: Wants] =====")
    for it in result["recommended_budget"]["wants"]:
        print(f"  {it['category']}: {it['recommended_amount']:,}원")

    print("\n===== [룰 기반 예산안: Savings] =====")
    for it in result["recommended_budget"]["savings"]:
        print(f"  {it['category']}: {it['recommended_amount']:,}원")

        # 5) 전체 결과 출력
    print("\n\n===== [전체 Response JSON] =====")
    pprint(result)