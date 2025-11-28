from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json

PLAN_TYPES = {
    "MAINTAIN": "현상 유지",
    "FRUGAL": "초절약 플랜",
    "SUPPORT": "수입 증대 플랜", 
    "INVESTMENT": "투자 플랜"
}

# KOSCOM STO 모의 데이터
KOSCOM_STO_PRODUCTS = [
    {
        "id": "STO_001",
        "name": "A음악저작권 STO",
        "annual_return": 0.07,
        "min_investment": 100000,
        "risk_level": "중위험",
        "description": "인기 K-POP 저작권 수익 배당",
        "recommended_period": 12
    },
    {
        "id": "STO_002", 
        "name": "B부동산 STO",
        "annual_return": 0.05,
        "min_investment": 500000,
        "risk_level": "저위험",
        "description": "안정적인 오피스텔 임대 수익",
        "recommended_period": 24
    }
]

# 장학금/지원금 모의 데이터
MOCK_SUPPORT_INFO = [
    {
        "id": 1,
        "name": "국가장학금 I유형",
        "amount": 3500000,
        "period": "학기당",
        "eligible": "소득 8분위 이하",
        "category": "장학금",
        "application_url": "https://www.kosaf.go.kr"
    },
    {
        "id": 2,
        "name": "근로장학금",
        "amount": 400000,
        "period": "월",
        "eligible": "재학생 (주 20시간 이하)",
        "category": "장학금",
        "application_url": "https://www.kosaf.go.kr"
    },
    {
        "id": 3,
        "name": "청년내일채움공제",
        "amount": 300000,
        "period": "월",
        "eligible": "중소기업 취업 청년",
        "category": "정부지원",
        "application_url": "https://www.work.go.kr"
    }
]

# 복리 계산
def calculate_compound_interest(
    principal: int,
    monthly_deposit: int,
    annual_rate: float,
    months: int
) -> int:
    """
    복리 계산 (월 적립식)
    
    공식: FV = P(1+r)^n + PMT * [((1+r)^n - 1) / r]
    - P: 원금 (principal)
    - PMT: 월 납입액 (monthly_deposit)
    - r: 월 이율 (annual_rate / 12)
    - n: 개월 수 (months)
    """
    if months <= 0:
        return principal
    
    monthly_rate = annual_rate / 12
    
    # 원금의 미래가치
    future_principal = principal * ((1 + monthly_rate) ** months)
    
    # 월 적립액의 미래가치
    if monthly_rate > 0:
        future_deposits = monthly_deposit * (((1 + monthly_rate) ** months - 1) / monthly_rate)
    else:
        future_deposits = monthly_deposit * months
    
    return int(future_principal + future_deposits)


def calculate_achievement_months(
    target_amount: int,
    current_amount: int,
    monthly_deposit: int,
    annual_rate: float = 0.0
) -> int:
    """목표 달성까지 필요한 개월 수 계산"""
    if monthly_deposit <= 0:
        return -1
    
    shortfall = target_amount - current_amount
    if shortfall <= 0:
        return 0
    
    if annual_rate == 0:
        return int(shortfall / monthly_deposit) + (1 if shortfall % monthly_deposit > 0 else 0)
    else:
        # 복리 적용 시 (이진 탐색)
        for month in range(1, 600):
            future_value = calculate_compound_interest(
                current_amount, monthly_deposit, annual_rate, month
            )
            if future_value >= target_amount:
                return month
        return -1


def select_best_sto_product(
    target_amount: int,
    period_months: int,
    current_amount: int
) -> Dict[str, Any]:
    """사용자 상황에 가장 적합한 STO 상품 선택"""
    suitable_products = []
    
    for sto in KOSCOM_STO_PRODUCTS:
        if current_amount >= sto["min_investment"]:
            period_diff = abs(sto["recommended_period"] - period_months)
            period_score = max(0, 100 - (period_diff * 2))
            return_score = sto["annual_return"] * 1000
            total_score = period_score + return_score
            
            suitable_products.append({
                **sto,
                "score": total_score
            })
    
    if suitable_products:
        suitable_products.sort(key=lambda x: x["score"], reverse=True)
        return suitable_products[0]
    else:
        return KOSCOM_STO_PRODUCTS[0]


def find_suitable_support(
    monthly_needed: int,
    event_name: str = ""
) -> Optional[Dict[str, Any]]:
    """필요 금액에 적합한 지원금 찾기"""
    suitable_supports = []
    
    for support in MOCK_SUPPORT_INFO:
        if support["period"] == "월":
            monthly_amount = support["amount"]
        elif support["period"] == "학기당":
            monthly_amount = support["amount"] / 4
        else:
            monthly_amount = 0
        
        # 필요 금액의 50% 이상 충당 가능한 지원금
        if monthly_amount >= monthly_needed * 0.5:
            suitable_supports.append({
                **support,
                "monthly_amount": int(monthly_amount)
            })
    
    if suitable_supports:
        suitable_supports.sort(key=lambda x: x["monthly_amount"])
        return suitable_supports[0]
    
    return None


def analyze_situation(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int
) -> Dict[str, Any]:
    """사용자 상황 종합 분석"""
    
    shortfall = target_amount - current_amount
    
    # 목표 달성에 필요한 월 저축액
    monthly_required = int(shortfall / period_months) if period_months > 0 else shortfall
    
    # 현재 저축액과의 차이
    monthly_gap = monthly_required - monthly_save_potential
    
    # 추가 필요 비율
    if monthly_save_potential > 0:
        gap_rate = (monthly_gap / monthly_save_potential) * 100
    else:
        gap_rate = 999 if monthly_gap > 0 else 0
    
    # 난이도 판단
    if monthly_gap <= 0:
        difficulty = "쉬움"
        priority_plans = ["MAINTAIN"]
    elif gap_rate <= 30:
        difficulty = "보통"
        priority_plans = ["FRUGAL"]
    elif gap_rate <= 70:
        difficulty = "어려움"
        priority_plans = ["FRUGAL", "SUPPORT"]
    else:
        difficulty = "매우 어려움"
        priority_plans = ["SUPPORT", "INVESTMENT"]
    
    # 투자 적합성
    investment_suitable = (
        target_amount >= 2000000 and
        period_months >= 6 and
        current_amount >= 100000
    )

    # 각 플랜 적합성
    plan_suitability = {
        "MAINTAIN": monthly_gap <= 0,
        "FRUGAL": gap_rate <= 100,
        "SUPPORT": gap_rate > 30,
        "INVESTMENT": investment_suitable and gap_rate > 20
    }
    
    support_needed = (gap_rate > 50)
    
    if period_months <= 6:
        timeline_pressure = "높음"
    elif period_months <= 12:
        timeline_pressure = "보통"
    else:
        timeline_pressure = "낮음"
    
    return {
        "difficulty": difficulty,
        "shortfall_amount": max(0, shortfall),
        "monthly_required": monthly_required,
        "monthly_gap": max(0, monthly_gap),
        "gap_rate": gap_rate,
        "priority_plans": priority_plans,
        "plan_suitability": plan_suitability,
        "investment_suitable": investment_suitable,
        "support_needed": support_needed,
        "timeline_pressure": timeline_pressure,
        "is_achievable_now": monthly_gap <= 0
    }


def generate_plan_maintain(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int
) -> Dict[str, Any]:
    """
    Plan 0: 현상 유지 (Baseline)
    실제로 모이는 금액 계산 (목표와 다를 수 있음)
    """
    
    # 실제 월 저축액 = 현재 저축 가능액
    actual_monthly = monthly_save_potential
    
    # 실제로 모이는 금액
    final_amount = current_amount + (actual_monthly * period_months)
    
    # 목표 대비 달성률
    achievement_rate = (final_amount / target_amount * 100) if target_amount > 0 else 0
    shortfall = max(0, target_amount - final_amount)
    
    # 실제 달성 기간
    if actual_monthly > 0 and shortfall > 0:
        expected_period = calculate_achievement_months(
            target_amount, current_amount, actual_monthly
        )
    else:
        expected_period = period_months
    
    is_recommended = (achievement_rate >= 100)
    
    tags = []
    if achievement_rate >= 100:
        tags.extend(["목표 달성", "추천"])
    elif achievement_rate >= 80:
        tags.extend([f"{int(achievement_rate)}% 달성", "거의 달성"])
    else:
        tags.append(f"{int(achievement_rate)}% 달성")
        if shortfall > 0:
            tags.append(f"{shortfall:,}원 부족")
    
    return {
        "plan_type": "MAINTAIN",
        "plan_title": "현상 유지",
        "description": f"현재 저축 속도 유지 시 {period_months}개월 후 {final_amount:,}원 예상 (목표의 {int(achievement_rate)}%)",
        "monthly_required": actual_monthly,
        "monthly_shortfall": 0,
        "final_estimated_asset": final_amount,
        "expected_period": expected_period,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": (
            f"{period_months}개월 후 목표 달성 예상" if achievement_rate >= 100
            else f"{expected_period}개월이면 목표 달성 가능" if expected_period > 0
            else "추가 저축 전략이 필요합니다"
        ),
        "plan_detail": {
            "shortfall": shortfall,
            "achievement_rate": int(achievement_rate),
            "variant_id": "maintain_baseline"
        }
    }


def generate_plan_frugal(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int,
    overspent_category: str = "소비",
    category_amount: int = 0
) -> Dict[str, Any]:
    """
    Plan A: 초절약 플랜
    실제로 절약 가능한 금액 기반 계산
    """
    
    # 1. 절약 가능 금액 추정
    if category_amount > 0:
        # 해당 카테고리의 20% 절약 가정
        monthly_savings = int(category_amount * 0.2)
    else:
        # 보수적 추정: 현재 저축액의 20% 추가 (전체 소비의 일부 절약)
        monthly_savings = int(monthly_save_potential * 0.2) if monthly_save_potential > 0 else 50000
    
    # 2. 실제 월 저축액
    actual_monthly = monthly_save_potential + monthly_savings
    
    # 3. 실제로 모이는 금액
    final_estimated_asset = current_amount + (actual_monthly * period_months)
    
    # 4. 목표 대비 달성률
    achievement_rate = (final_estimated_asset / target_amount * 100) if target_amount > 0 else 0
    shortfall = max(0, target_amount - final_estimated_asset)
    
    # 5. 실제 달성 기간
    if actual_monthly > 0:
        expected_period = calculate_achievement_months(
            target_amount, current_amount, actual_monthly
        )
    else:
        expected_period = -1
    
    # 6. 추천 판단 (80% 이상이면 추천)
    is_recommended = (achievement_rate >= 50)
    
    tags = [f"월 {monthly_savings:,}원 절약"]
    if achievement_rate >= 100:
        tags.append("목표 달성")
        tags.append("강력 추천")
    elif achievement_rate >= 80:
        tags.append("거의 달성")
        tags.append("추천")
    elif achievement_rate >= 50:
        tags.append("절반 달성")
        tags.append("추천")
    else:
        tags.append(f"{int(achievement_rate)}% 달성")
    
    return {
        "plan_type": "FRUGAL",
        "plan_title": "초절약 플랜",
        "description": f"{overspent_category} 지출 20% 줄이면 월 {monthly_savings:,}원 절약",
        "monthly_required": actual_monthly,
        "monthly_shortfall": max(0, shortfall // period_months) if period_months > 0 else 0,
        "final_estimated_asset": final_estimated_asset,
        "expected_period": expected_period,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": (
            f"{period_months}개월 후 {final_estimated_asset:,}원 예상 (목표의 {int(achievement_rate)}%)"
        ),
        "next_tool": "recommend_budget",
        "plan_detail": {
            "monthly_savings": monthly_savings,
            "achievement_rate": int(achievement_rate),
            "shortfall": shortfall,
            "target_categories": [overspent_category],
            "variant_id": "frugal_all_categories"
        }
    }


def generate_plan_support(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int,
    event_name: str
) -> Dict[str, Any]:
    """
    Plan B: 수입 증대 플랜
    지원금으로 실제 가능한 금액 계산
    """
    
    shortfall = target_amount - current_amount
    monthly_needed = int(shortfall / period_months) if period_months > 0 else shortfall
    monthly_gap = max(0, monthly_needed - monthly_save_potential)
    
    suitable_support = find_suitable_support(monthly_gap, event_name)
    
    if suitable_support:
        # 지원금 받을 경우 실제 월 저축액
        actual_monthly = monthly_save_potential + suitable_support["monthly_amount"]
    else:
        # 보수적 추정: 월 20만원 추가 수입 가정
        actual_monthly = monthly_save_potential + 200000
    
    # 실제로 모이는 금액
    final_estimated_asset = current_amount + (actual_monthly * period_months)
    
    # 목표 대비 달성률
    achievement_rate = (final_estimated_asset / target_amount * 100) if target_amount > 0 else 0
    shortfall_final = max(0, target_amount - final_estimated_asset)
    
    # 실제 달성 기간
    if actual_monthly > 0:
        expected_period = calculate_achievement_months(
            target_amount, current_amount, actual_monthly
        )
    else:
        expected_period = -1
    
    is_recommended = (suitable_support is not None and achievement_rate >= 80)
    
    tags = ["소비 유지"]
    if suitable_support:
        tags.append(f"월 {suitable_support['monthly_amount']:,}원 추가")
        if achievement_rate >= 100:
            tags.append("목표 달성")
            tags.append("추천")
        elif achievement_rate >= 80:
            tags.append("거의 달성")
            tags.append("추천")
    else:
        tags.append("지원금 탐색 필요")
    
    return {
        "plan_type": "SUPPORT",
        "plan_title": "수입 증대 플랜",
        "description": (
            f"{suitable_support['name']} 활용 시 월 {suitable_support['monthly_amount']:,}원 추가 수입"
            if suitable_support
            else "장학금이나 알바로 월 수입 증대 필요"
        ),
        "monthly_required": actual_monthly,
        "monthly_shortfall": max(0, shortfall_final // period_months) if period_months > 0 else 0,
        "final_estimated_asset": final_estimated_asset,
        "expected_period": expected_period,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": (
            f"{period_months}개월 후 {final_estimated_asset:,}원 예상 (목표의 {int(achievement_rate)}%)"
        ),
        "support_info": suitable_support,
        "next_tool": "get_support_info",
        "plan_detail": {
            "support_found": suitable_support is not None,
            "achievement_rate": int(achievement_rate),
            "shortfall": shortfall_final,
            "search_keywords": [event_name, "대학생", "청년", "장학금"] if event_name else ["대학생", "청년"],
            "variant_id": "support_scholarship"
        }
    }


def generate_plan_investment(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int
) -> Dict[str, Any]:
    """
    Plan C: KOSCOM 투자 플랜
    투자 수익 포함한 실제 예상 금액 계산
    """
    
    selected_sto = select_best_sto_product(
        target_amount, period_months, current_amount
    )
    
    # 투자 시 필요한 월 저축액 (복리 역산)
    shortfall = target_amount - current_amount
    
    # 단순 계산으로 추정
    monthly_required = monthly_save_potential
    
    # 실제로 모이는 금액 (복리)
    final_amount = calculate_compound_interest(
        current_amount, monthly_required,
        selected_sto["annual_return"], period_months
    )
    
    # 목표 대비 달성률
    achievement_rate = (final_amount / target_amount * 100) if target_amount > 0 else 0
    shortfall_final = max(0, target_amount - final_amount)
    
    # 일반 저축 대비 이득
    simple_total = current_amount + (monthly_required * period_months)
    investment_profit = final_amount - simple_total
    
    # 절감 효율
    simple_monthly_needed = int(shortfall / period_months) if period_months > 0 else shortfall
    monthly_saved = max(0, simple_monthly_needed - monthly_required)
    
    if simple_monthly_needed > 0:
        efficiency = (monthly_saved / simple_monthly_needed) * 100
    else:
        efficiency = 0
    
    # 실제 달성 기간
    if monthly_required > 0:
        for month in range(1, 600):
            future_value = calculate_compound_interest(
                current_amount, monthly_required,
                selected_sto["annual_return"], month
            )
            if future_value >= target_amount:
                expected_period = month
                break
        else:
            expected_period = -1
    else:
        expected_period = -1
    
    # 추천 판단
    is_recommended = (
        target_amount >= 2000000 and
        period_months >= 6 and
        achievement_rate >= 80
    )
    
    tags = [f"연 {int(selected_sto['annual_return']*100)}%", selected_sto['risk_level']]
    if achievement_rate >= 100:
        tags.append("목표 달성")
        if is_recommended:
            tags.append("추천")
    elif achievement_rate >= 80:
        tags.append("거의 달성")
        if is_recommended:
            tags.append("추천")
    else:
        tags.append(f"{int(achievement_rate)}% 달성")
    
    risk_warnings = []
    if period_months < selected_sto["recommended_period"]:
        risk_warnings.append(f"권장 기간({selected_sto['recommended_period']}개월)보다 짧아 변동성 위험")
    if selected_sto["risk_level"] == "중위험":
        risk_warnings.append("원금 손실 가능성 존재")
    
    return {
        "plan_type": "INVESTMENT",
        "plan_title": "투자 플랜",
        "description": f"{selected_sto['name']} 투자 시 {period_months}개월 후 {final_amount:,}원 예상",
        "monthly_required": monthly_required,
        "monthly_shortfall": max(0, shortfall_final // period_months) if period_months > 0 else 0,
        "final_estimated_asset": final_amount,
        "expected_period": expected_period if expected_period > 0 else period_months,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": (
            f"예상 투자 수익 {investment_profit:,}원 (목표의 {int(achievement_rate)}%)"
        ),
        "sto_product": {
            "id": selected_sto["id"],
            "name": selected_sto["name"],
            "annual_return": selected_sto["annual_return"],
            "risk_level": selected_sto["risk_level"],
            "description": selected_sto["description"]
        },
        "investment_profit": investment_profit,
        "monthly_saved": monthly_saved,
        "plan_detail": {
            "simple_monthly": simple_monthly_needed,
            "investment_monthly": monthly_required,
            "efficiency": round(efficiency, 1),
            "achievement_rate": int(achievement_rate),
            "shortfall": shortfall_final,
            "risk_warnings": risk_warnings,
            "variant_id": "investment_music_copyright"
        }
    }


def generate_all_plans(
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: int,
    monthly_save_potential: int,
    overspent_category: str = "소비",
    category_amount: int = 0
) -> List[Dict[str, Any]]:
    """모든 플랜 생성"""
    
    return [
        generate_plan_maintain(
            current_amount, target_amount, period_months, monthly_save_potential
        ),
        generate_plan_frugal(
            current_amount, target_amount, period_months, monthly_save_potential,
            overspent_category, category_amount
        ),
        generate_plan_support(
            current_amount, target_amount, period_months, monthly_save_potential, event_name
        ),
        generate_plan_investment(
            current_amount, target_amount, period_months, monthly_save_potential
        )
    ]


def simulate_event(
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: int,
    monthly_save_potential: int,
    auto_select: bool = False,
    overspent_category: str = "소비",
    category_amount: int = 0
) -> Dict[str, Any]:
    """시뮬레이션 메인 함수"""
    
    try:
        if target_amount <= 0:
            return {"error": "목표 금액은 0보다 커야 합니다."}
        
        if period_months <= 0:
            return {"error": "목표 기간은 0보다 커야 합니다."}
        
        # 상황 분석
        situation = analyze_situation(
            current_amount, target_amount, period_months, monthly_save_potential
        )
        
        # 플랜 생성
        if auto_select:
            plans = [generate_plan_maintain(
                current_amount, target_amount, period_months, monthly_save_potential
            )]

            if situation["plan_suitability"]["FRUGAL"]:
                plans.append(generate_plan_frugal(
                    current_amount, target_amount, period_months, monthly_save_potential,
                    overspent_category, category_amount
                ))
            
            if situation["plan_suitability"]["SUPPORT"]:
                plans.append(generate_plan_support(
                    current_amount, target_amount, period_months, 
                    monthly_save_potential, event_name
                ))
            
            if situation["plan_suitability"]["INVESTMENT"]:
                plans.append(generate_plan_investment(
                    current_amount, target_amount, period_months, monthly_save_potential
                ))
        else:
            plans = generate_all_plans(
                event_name, target_amount, period_months,
                current_amount, monthly_save_potential,
                overspent_category, category_amount
            )
        
        return {
            "event_name": event_name,
            "target_amount": target_amount,
            "current_amount": current_amount,
            "shortfall_amount": situation["shortfall_amount"],
            "period_months": period_months,
            "monthly_save_potential": monthly_save_potential,
            "situation_analysis": situation,
            "plans": plans,
            "simulation_date": datetime.now().strftime("%Y-%m-%d"),
            "meta": {
                "plans_count": len(plans),
                "recommended_plans": [p["plan_type"] for p in plans if p["is_recommended"]]
            }
        }
        
    except Exception as e:
        return {"error": f"시뮬레이션 중 오류: {str(e)}"}


if __name__ == "__main__":
    print("=" * 80)
    print("현실적 시뮬레이션 Tool - 테스트")
    print("=" * 80)
    
    test = {
        "event_name": "유럽 여행",
        "target_amount": 5000000,
        "period_months": 12,
        "current_amount": 0,
        "monthly_save_potential": 300000,
        "overspent_category": "카페/디저트",
        "category_amount": 150000
    }
    
    result = simulate_event(**test, auto_select=False)
    
    if "error" not in result:
        sit = result["situation_analysis"]
        print(f"\n상황 분석:")
        print(f"  난이도: {sit['difficulty']}")
        print(f"  부족액: {sit['shortfall_amount']:,}원")
        print(f"  필요 월 저축: {sit['monthly_required']:,}원")
        
        print(f"\n생성된 플랜: {result['meta']['plans_count']}개")
        for i, plan in enumerate(result['plans'], 1):
            status = "✅ 추천" if plan['is_recommended'] else "❌ 비추천"
            print(f"\n  [{i}] {plan['plan_title']} {status}")
            print(f"      월 저축: {plan['monthly_required']:,}원")
            print(f"      최종 예상: {plan['final_estimated_asset']:,}원")
            print(f"      달성률: {plan['plan_detail']['achievement_rate']}%")
            print(f"      예상 기간: {plan['expected_period']}개월")
    else:
        print(f"오류: {result['error']}")