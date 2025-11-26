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
        "annual_return": 0.07,  # 연 7%
        "min_investment": 100000,
        "risk_level": "중위험",
        "description": "인기 K-POP 저작권 수익 배당",
        "recommended_period": 12  # 권장 투자 기간(개월)
    },
    {
        "id": "STO_002", 
        "name": "B부동산 STO",
        "annual_return": 0.05,  # 연 5%
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


# 역산 로직
def calculate_monthly_required(
    target_amount: int,
    current_amount: int,
    months: int,
    annual_rate: float = 0.0
) -> int:
    """
    목표 달성을 위한 월 저축액 계산
    
    Args:
        target_amount: 목표 금액
        current_amount: 현재 보유 금액
        months: 목표 기간(개월)
        annual_rate: 연 이율 (투자 시)
    
    Returns:
        필요한 월 저축액
    """
    if months <= 0:
        return max(0, target_amount - current_amount)
    
    shortfall = target_amount - current_amount
    
    if shortfall <= 0:
        return 0
    
    if annual_rate == 0:
        # 단순 저축
        return int(shortfall / months)
    else:
        # 복리 적용 시 (역계산)
        monthly_rate = annual_rate / 12
        
        # 현재 금액의 미래 가치
        future_current = current_amount * ((1 + monthly_rate) ** months)
        remaining = target_amount - future_current

        if remaining <= 0:
            return 0
        
        # 필요한 월 저축액 (적립식 연금 역계산)
        if monthly_rate > 0:
            monthly_required = remaining / (((1 + monthly_rate) ** months - 1) / monthly_rate)
        else:
            monthly_required = remaining / months
        
        return max(0, int(monthly_required))


def calculate_achievement_months(
    target_amount: int,
    current_amount: int,
    monthly_deposit: int,
    annual_rate: float = 0.0
) -> int:
    """
    목표 달성까지 필요한 개월 수 계산
    
    Returns:
        필요 개월 수 (-1: 달성 불가)
    """
    if monthly_deposit <= 0:
        return -1
    
    shortfall = target_amount - current_amount
    if shortfall <= 0:
        return 0
    
    if annual_rate == 0:
        # 단순 계산
        return int(shortfall / monthly_deposit) + 1
    else:
        # 복리 적용 시 (이진 탐색으로 근사)
        for month in range(1, 600):  # 최대 50년
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
    """
    사용자 상황에 가장 적합한 STO 상품 선택
    
    선택 기준:
    1. 최소 투자금액 조건 만족
    2. 권장 기간과 사용자 기간 비교
    3. 수익률 우선
    """
    suitable_products = []
    
    for sto in KOSCOM_STO_PRODUCTS:
        if current_amount >= sto["min_investment"]:
            # 기간 적합도 점수 (권장 기간과 차이가 적을수록 높음)
            period_diff = abs(sto["recommended_period"] - period_months)
            period_score = max(0, 100 - (period_diff * 2))
            
            # 수익률 점수
            return_score = sto["annual_return"] * 1000
            
            # 종합 점수
            total_score = period_score + return_score
            
            suitable_products.append({
                **sto,
                "score": total_score
            })
    
    if suitable_products:
        # 점수 높은 순 정렬 후 1위 반환
        suitable_products.sort(key=lambda x: x["score"], reverse=True)
        return suitable_products[0]
    else:
        # 기본값 (조건 불만족 시)
        return KOSCOM_STO_PRODUCTS[0]

def find_suitable_support(
    monthly_needed: int,
    event_name: str = ""
) -> Optional[Dict[str, Any]]:
    """
    필요 금액에 적합한 지원금 찾기
    
    Returns:
        적합한 지원금 정보 또는 None
    """
    suitable_supports = []
    
    for support in MOCK_SUPPORT_INFO:
        # 월 환산
        if support["period"] == "월":
            monthly_amount = support["amount"]
        elif support["period"] == "학기당":
            monthly_amount = support["amount"] / 4  # 4개월로 환산
        else:
            monthly_amount = 0
        
        # 필요 금액 이상인 지원금만
        if monthly_amount >= monthly_needed:
            suitable_supports.append({
                **support,
                "monthly_amount": int(monthly_amount)
            })
    
    if suitable_supports:
        # 금액이 딱 맞는 순으로 정렬 (과도하게 많은 것 제외)
        suitable_supports.sort(key=lambda x: x["monthly_amount"])
        return suitable_supports[0]
    
    return None


# ========================================
#  헬퍼 함수 (AI Service용)
# ========================================

def analyze_situation(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int
) -> Dict[str, Any]:
    """
    사용자 상황 종합 분석
    
    AI가 이 결과를 보고 어떤 플랜을 생성할지 결정
    
    Returns:
        {
            "difficulty": "쉬움" | "보통" | "어려움" | "매우 어려움",
            "shortfall_amount": 부족 금액,
            "monthly_required": 필요 월 저축액,
            "monthly_gap": 추가 필요액,
            "gap_rate": 추가 필요 비율(%),
            "recommended_plans": ["MAINTAIN", "FRUGAL", ...],
            "investment_suitable": True/False,
            "support_needed": True/False,
            "timeline_pressure": "높음" | "보통" | "낮음"
        }
    """
    
    shortfall = target_amount - current_amount
    
    # 목표 달성에 필요한 월 저축액 (단순 저축)
    monthly_required = calculate_monthly_required(
        target_amount, current_amount, period_months, 0.0
    )
    
    # 현재 저축액과의 차이
    monthly_gap = monthly_required - monthly_save_potential
    
    # 추가 필요 비율 (%)
    if monthly_save_potential > 0:
        gap_rate = (monthly_gap / monthly_save_potential) * 100
    else:
        gap_rate = 999 if monthly_gap > 0 else 0
    
    # 난이도 판단
    if monthly_gap <= 0:
        difficulty = "쉬움"
        priority_plans = ["MAINTAIN"]  # 이름 변경: 우선순위일 뿐
    elif gap_rate <= 30:
        difficulty = "보통"
        priority_plans = ["FRUGAL"]
    elif gap_rate <= 70:
        difficulty = "어려움"
        priority_plans = ["FRUGAL", "SUPPORT"]
    else:
        difficulty = "매우 어려움"
        priority_plans = ["SUPPORT", "INVESTMENT"]
    
    # 투자 적합성 판단
    investment_suitable = (
        target_amount >= 2000000 and  # 200만원 이상
        period_months >= 6 and        # 6개월 이상
        current_amount >= 100000      # STO 최소 투자금액
    )

    # 각 플랜의 적합성 판단
    plan_suitability = {
        "MAINTAIN": monthly_gap <= 0,  # 현재로도 달성 가능할 때만
        "FRUGAL": gap_rate <= 100,     # 2배까지는 절약으로 가능
        "SUPPORT": gap_rate > 30,      # 30% 이상 부족 시 유용
        "INVESTMENT": investment_suitable and gap_rate > 20  # 투자 조건 + 20% 이상 부족
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

# ========================================
#  플랜 생성 함수들 (AI가 선택적으로 호출)
# ========================================

def generate_plan_maintain(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int
) -> Dict[str, Any]:
    """
    Plan 0: 현상 유지 (Baseline)
    
    특징:
    - 아무런 변화 없이 현재 저축액만 모음
    - 다른 플랜들의 비교 기준점 (Baseline) 역할
    
    AI 판단 기준:
    - 항상 생성 (비교 기준이므로)
    - 단, 목표 달성 가능 시 추천
    """
    
    final_amount = current_amount + (monthly_save_potential * period_months)
    shortfall = target_amount - final_amount
    
    # 실제 달성 기간
    if shortfall > 0 and monthly_save_potential > 0:
        expected_period = calculate_achievement_months(
            target_amount, current_amount, monthly_save_potential
        )
    else:
        expected_period = period_months
    
    is_recommended = (shortfall <= 0)
    
    tags = []
    if is_recommended:
        tags.extend(["달성 가능", "안정적"])
    else:
        tags.append("비추천")
        if shortfall > 0:
            tags.append(f"{shortfall:,}원 부족")
    
    return {
        "plan_type": "MAINTAIN",
        "plan_title": "현상 유지",
        "description": (
            f"현재 상태를 유지하면 {period_months}개월 뒤 {final_amount:,}원을 모을 수 있습니다. " +
            (f"목표까지 {shortfall:,}원이 부족합니다." if shortfall > 0
             else "목표를 달성할 수 있습니다!")
        ),
        "monthly_required": monthly_save_potential,
        "monthly_shortfall": 0,
        "final_estimated_asset": final_amount,
        "expected_period": expected_period,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": (
            "현재 저축 습관을 유지하시면 됩니다!" if is_recommended
            else "현재 속도로는 목표 달성이 어렵습니다. 다른 전략이 필요합니다."
        ),
        "plan_detail": {
            "shortfall": shortfall,
            "achievement_rate": int((final_amount / target_amount) * 100) if target_amount > 0 else 0
        }
    }


def generate_plan_frugal(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int
) -> Dict[str, Any]:
    """
    Plan A: 초절약 플랜 (Frugal/Budgeting)
    
    특징:
    - 투자나 추가 수입 없이 오직 절약만으로 목표 달성
    - 예산 조정 Tool (recommend_budget) 연동 필수
    
    AI 판단 기준:
    - 월 추가 필요액이 현재 저축액의 50% 이하 → 추천
    - 50~100% → 보통 (도전적)
    - 100% 이상 → 비추천 (비현실적)
    """
    
    monthly_required = calculate_monthly_required(
        target_amount, current_amount, period_months, 0.0
    )
    
    monthly_shortfall = max(0, monthly_required - monthly_save_potential)
    final_amount = target_amount
    
    # 추천 판단: 추가 필요액이 현재 저축액의 몇 %?
    if monthly_save_potential > 0:
        additional_rate = (monthly_shortfall / monthly_save_potential) * 100
    else:
        additional_rate = 999
    
    is_recommended = (additional_rate <= 50)
    
    if additional_rate <= 20:
        difficulty = "쉬움"
        tags = ["추천", "현실적", "안전함"]
    elif additional_rate <= 50:
        difficulty = "보통"
        tags = ["도전적", "안전함"]
    else:
        difficulty = "어려움"
        tags = ["고난이도", "비추천"]
    
    if monthly_shortfall > 0:
        tags.append(f"월 +{monthly_shortfall:,}원")
    
    return {
        "plan_type": "FRUGAL",
        "plan_title": "초절약 플랜",
        "description": (
            f"투자 없이 예산 조정만으로 목표를 달성합니다. "
            f"월 {monthly_required:,}원을 저축하면 {period_months}개월 안에 달성 가능합니다."
        ),
        "monthly_required": monthly_required,
        "monthly_shortfall": monthly_shortfall,
        "final_estimated_asset": final_amount,
        "expected_period": period_months,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": (
            "현재 저축액만으로도 충분합니다!" if monthly_shortfall == 0
            else f"월 {monthly_shortfall:,}원을 추가로 저축해야 합니다. 예산을 조정해보세요."
        ),
        "next_tool": "recommend_budget",
        "plan_detail": {
            "additional_rate": round(additional_rate, 1),
            "difficulty": difficulty,
            "target_categories": ["카페/디저트", "사회/모임", "쇼핑/꾸미기"]
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
    Plan B: 수입 증대 플랜 (Support)
    
    특징:
    - 현재 소비 패턴 유지
    - 장학금/지원금으로 부족분 충당
    - 금융 상담 Tool (get_support_info) 연동 필수
    
    AI 판단 기준:
    - 적합한 지원금을 찾았을 때 → 추천
    - 못 찾았을 때 → 비추천 (단, 상담봇 안내)
    """
    
    monthly_required = calculate_monthly_required(
        target_amount, current_amount, period_months, 0.0
    )
    
    monthly_shortfall = max(0, monthly_required - monthly_save_potential)
    suitable_support = find_suitable_support(monthly_shortfall, event_name)
    final_amount = target_amount
    
    is_recommended = (suitable_support is not None)
    
    tags = ["소비 유지"]
    if suitable_support:
        tags.append("추천")
        tags.append(suitable_support["name"])
    else:
        tags.append("지원금 탐색 필요")
        tags.append("AICC 상담 권장")
    
    return {
        "plan_type": "SUPPORT",
        "plan_title": "수입 증대 플랜",
        "description": (
            f"현재 소비를 유지하면서 월 {monthly_shortfall:,}원의 추가 수입이 필요합니다. "
            f"장학금이나 정부 지원금을 활용하세요."
        ),
        "monthly_required": monthly_required,
        "monthly_shortfall": monthly_shortfall,
        "final_estimated_asset": final_amount,
        "expected_period": period_months,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": (
            f"'{suitable_support['name']}'을 신청하면 월 {suitable_support['monthly_amount']:,}원을 받을 수 있습니다!" 
            if suitable_support
            else "KOSCOM AICC 금융 상담봇으로 맞춤 지원금을 찾아보세요."
        ),
        "support_info": suitable_support,
        "next_tool": "get_support_info",
        "plan_detail": {
            "support_found": suitable_support is not None,
            "search_keywords": [event_name, "대학생", "청년", "장학금"] if event_name else ["대학생", "청년"]
        }
    }


def generate_plan_investment(
    current_amount: int,
    target_amount: int,
    period_months: int,
    monthly_save_potential: int
) -> Dict[str, Any]:
    """
    Plan C: KOSCOM 투자 플랜 (Investment)
    
    특징:
    - KOSCOM STO/RA 상품 활용
    - 복리 효과로 필요 저축액 감소
    - 리스크 존재 (명시 필요)
    
    AI 판단 기준:
    - 목표 금액 200만원 이상 + 기간 6개월 이상 → 추천 고려
    - 소액 단기 목표 → 비추천 (수수료/변동성 불리)
    - 투자 수익이 월 1만원 이상 절감 효과 → 추천
    """
    
    # 가장 적합한 STO 선택
    selected_sto = select_best_sto_product(
        target_amount, period_months, current_amount
    )
    
    # 투자 수익 고려 월 저축액
    monthly_required = calculate_monthly_required(
        target_amount, current_amount, period_months,
        selected_sto["annual_return"]
    )
    
    monthly_shortfall = max(0, monthly_required - monthly_save_potential)
    
    # 최종 자산 (복리)
    final_amount = calculate_compound_interest(
        current_amount, monthly_required,
        selected_sto["annual_return"], period_months
    )
    
    # 일반 저축 대비 이득
    simple_monthly = calculate_monthly_required(
        target_amount, current_amount, period_months, 0.0
    )
    monthly_saved = simple_monthly - monthly_required
    
    # 투자 수익
    simple_total = current_amount + (monthly_required * period_months)
    investment_profit = final_amount - simple_total
    
    # 절감 효율 (%)
    if simple_monthly > 0:
        efficiency = (monthly_saved / simple_monthly) * 100
    else:
        efficiency = 0
    
    # 추천 판단
    is_recommended = (
        target_amount >= 2000000 and  # 200만원 이상
        period_months >= 6 and        # 6개월 이상
        efficiency >= 5               # 5% 이상 효율 (비율 기반)
    )
    
    tags = ["고효율", f"연 {int(selected_sto['annual_return']*100)}%"]
    if is_recommended:
        tags.append("추천")
        tags.append(f"월 {monthly_saved:,}원 절감")
    else:
        if period_months < 6:
            tags.append("단기 부적합")
        else:
            tags.append("신중 검토")
    
    risk_warnings = []
    if period_months < selected_sto["recommended_period"]:
        risk_warnings.append(f"권장 기간({selected_sto['recommended_period']}개월)보다 짧아 변동성 위험 있음")
    if selected_sto["risk_level"] == "중위험":
        risk_warnings.append("원금 손실 가능성 존재 (시장 상황에 따라 변동)")
    
    return {
        "plan_type": "INVESTMENT",
        "plan_title": "투자 플랜",
        "description": (
            f"KOSCOM {selected_sto['name']}에 투자하면 "
            f"일반 저축보다 월 {monthly_saved:,}원 덜 저축해도 됩니다."
        ),
        "monthly_required": monthly_required,
        "monthly_shortfall": monthly_shortfall,
        "final_estimated_asset": final_amount,
        "expected_period": period_months,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": (
            f"{period_months}개월 뒤 예상 투자 수익은 {investment_profit:,}원입니다. "
            f"투자 효율은 {efficiency:.1f}%이지만, 리스크가 있으니 신중히 결정하세요."
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
            "simple_monthly": simple_monthly,
            "investment_monthly": monthly_required,
            "efficiency": round(efficiency, 1),
            "risk_warnings": risk_warnings
        }
    }


def generate_all_plans(
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: int,
    monthly_save_potential: int
) -> List[Dict[str, Any]]:
    """
    모든 플랜 생성 (테스트용 또는 AI가 전체 옵션을 보고 싶을 때)
    
    Note:
        실제 운영에서는 AI가 analyze_situation() 결과를 보고
        필요한 generate_plan_xxx() 함수만 선택적으로 호출하는 것을 권장
    """
    
    return [
        generate_plan_maintain(
            current_amount, target_amount, period_months, monthly_save_potential
        ),
        generate_plan_frugal(
            current_amount, target_amount, period_months, monthly_save_potential
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
    auto_select: bool = False
) -> Dict[str, Any]:
    """
    시뮬레이션 메인 함수
    
    Args:
        event_name: 이벤트 이름
        target_amount: 목표 금액
        period_months: 목표 기간
        current_amount: 현재 금액
        monthly_save_potential: 월 저축 가능액
        auto_select: True면 AI 대신 자동 선택 (테스트용)
    
    Returns:
        시뮬레이션 결과
    
    Note:
        실제 운영에서는 AI Service가 이 함수 대신
        analyze_situation() + 개별 generate_plan_xxx()를 직접 호출
    """
    
    try:
        # 입력 검증
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
            # 자동 선택 모드 (적합성 기반)
            plans = [generate_plan_maintain(
                current_amount, target_amount, period_months, monthly_save_potential
            )]

            if situation["plan_suitability"]["FRUGAL"]:
                plans.append(generate_plan_frugal(
                    current_amount, target_amount, period_months, monthly_save_potential
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
            # 전체 생성
            plans = generate_all_plans(
                event_name, target_amount, period_months,
                current_amount, monthly_save_potential
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


# ========================================
#  테스트 코드
# ========================================

if __name__ == "__main__":
    print("=" * 80)
    print("시뮬레이션 Tool - 최종 완성 버전 테스트")
    print("=" * 80)
    
    tests = [
        {
            "name": "대규모 목표 (교환학생 800만원)",
            "params": {
                "event_name": "교환학생",
                "target_amount": 8000000,
                "period_months": 12,
                "current_amount": 500000,
                "monthly_save_potential": 300000,
                "auto_select": True
            }
        },
        {
            "name": "소액 단기 (노트북 250만원)",
            "params": {
                "event_name": "노트북 구매",
                "target_amount": 2500000,
                "period_months": 3,
                "current_amount": 1000000,
                "monthly_save_potential": 400000,
                "auto_select": True
            }
        }
    ]
    
    for test in tests:
        print(f"\n{'='*80}")
        print(f"[테스트] {test['name']}")
        print(f"{'='*80}")
        
        result = simulate_event(**test["params"])
        
        if "error" in result:
            print(f"오류: {result['error']}")
            continue
        
        sit = result["situation_analysis"]
        print(f"\n상황 분석:")
        print(f"  - 난이도: {sit['difficulty']}")
        print(f"  - 부족액: {sit['shortfall_amount']:,}원")
        print(f"  - 필요 월 저축: {sit['monthly_required']:,}원")
        print(f"  - 추가 필요: {sit['monthly_gap']:,}원 ({sit['gap_rate']:.1f}%)")
        print(f"  - AI 추천: {', '.join(sit['priority_plans'])}")
        
        print(f"\n📋 생성된 플랜: {result['meta']['plans_count']}개")
        for i, plan in enumerate(result['plans'], 1):
            status = "추천" if plan['is_recommended'] else "비추천"
            print(f"  [{i}] {plan['plan_title']} {status}")
            print(f"      태그: {', '.join(plan['tags'])}")
            print(f"      월 저축: {plan['monthly_required']:,}원")
    
    print(f"\n{'='*80}")
    print("테스트 완료!")
    print(f"{'='*80}")