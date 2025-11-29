from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json
from sqlmodel import Session, select
from backend.models.support import SupportPolicy, SupportCategory

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
        "name": "강남 역삼 오피스 빌딩 1호",
        "annual_return": 0.055, # 카사(Kasa) 등 부동산 조각투자 평균 배당+매각 수익률 고려 (약 5~6%대)
        "min_investment": 5000, # 통상적인 부동산 DABS 1주 공모가
        "risk_level": "저위험",
        "description": "강남 업무지구 핵심 입지의 오피스 빌딩 임대 배당 및 매각 차익",
        "recommended_period": 24
    },
    {
        "id": "STO_002", 
        "name": "K-POP 음원 저작권료 신탁수익증권",
        "annual_return": 0.08, # 뮤직카우 등 저작권료 배당 기대 수익률 (약 8%)
        "min_investment": 10000, # 음원 저작권 1주 단위 통상 가격
        "risk_level": "중위험",
        "description": "글로벌 팬덤을 보유한 K-POP 아티스트의 음원 저작권료 수익 배당",
        "recommended_period": 12
    },
    {
        "id": "STO_003",
        "name": "프리미엄 한우 송아지 사육 투자",
        "annual_return": 0.09, # 뱅카우 2024년 공모 상품 목표 수익률(8~9%) 반영
        "min_investment": 20000, # 뱅카우 공모가 1주 2만원 반영
        "risk_level": "고위험", # 생물 자산 특성(폐사, 등급 하락 등) 반영
        "description": "철저한 관리하에 사육되는 1등급 한우의 경매 매각 수익 배분",
        "recommended_period": 30 # 한우 평균 사육 기간 (약 30개월)
    },
    {
        "id": "STO_004",
        "name": "글로벌 블루칩 미술품 조각투자",
        "annual_return": 0.12, # 테사 등 미술품 조각투자 과거 평균 목표 수익률 반영
        "min_investment": 1000, # 소액 투자 가능성 반영 (1천원 단위)
        "risk_level": "고위험", # 예술품 시장 유동성 리스크 및 가격 변동성 반영
        "description": "세계적인 거장의 검증된 미술 작품 소유권 분할 투자 및 매각 차익",
        "recommended_period": 12
    }
]

CATEGORY_SAVING_RATES = {
    # 필수 지출 (줄이기 어려움)
    "식사": 0.15,        # (식비, 편의점) -> 15% 절약
    "교통": 0.10,        # (교통, 택시) -> 10% 절약
    "주거": 0.05,        # (주거, 월세) -> 5% 절약
    "통신/구독": 0.20,   # (통신, 구독) -> 20% 절약 (요금제 변경/해지)
    "교육/학습": 0.10,   # (학원, 도서) -> 10% 절약

    # 선택 지출 (줄이기 쉬움)
    "카페/디저트": 0.40, # (카페) -> 40% 절약
    "쇼핑/꾸미기": 0.30, # (쇼핑, 패션, 뷰티) -> 30% 절약
    "사회/모임": 0.30,   # (술집, 회식) -> 30% 절약
    "취미/여가": 0.30,   # (영화, 노래방) -> 30% 절약
}

DEFAULT_SAVING_RATE = 0.20
AGGRESSIVE_SAVING_RATE = 0.35

def estimate_policy_amount(policy: SupportPolicy) -> int:
    """
    정책 데이터를 기반으로 '월 단위 실질 지원 효과(금액)'를 추정합니다.
    DB에 있는 모든 리스트를 반영했습니다.
    """
    title = policy.title.strip()
    
    # -------------------------------------------------------
    # [1] 장학금 / 등록금 지원 (Scholarship)
    # -------------------------------------------------------
    if "국가장학금 I유형" in title:
        # 연간 최대 350만원 -> 월 약 29만원
        return 3500000 // 12
    if "국가장학금 II유형" in title:
        # 대학별 상이, 평균적으로 월 10만원 수준 가정
        return 100000
    if "교내 근로장학금" in title:
        # 월 평균 40~60만원 -> 최소 기준 40만원
        return 400000
    if "국가근로장학금" in title:
        # 시급 1만원대, 월 20시간 가정 시 -> 약 20만원 (보수적 접근)
        return 200000
    if "청년 월세 지원" in title: # (국토부, 지자체 공통)
        # 월 최대 20만원
        return 200000
    if "청년 생활안정지원금" in title:
        # 지자체별 상이, 1회성인 경우도 있으나 월 환산 약 5만원 가정
        return 50000
    if "서울 청년수당" in title:
        # 월 50만원 x 6개월 -> 월 50만원
        return 500000

    # -------------------------------------------------------
    # [2] 대출 (Loan) - 이자 절감 효과는 있으나 '수입'은 아니므로 제외
    # -------------------------------------------------------
    # 학자금 대출, 햇살론, 전세자금 대출 등은 
    # '자산 형성' 시뮬레이션에서는 부채로 잡히거나 유동성 확보용이므로
    # 월 저축 가능액을 늘려주는 '지원금'으로는 계산하지 않음 (0원)
    
    # -------------------------------------------------------
    # [3] 생활 / 주거 (Living)
    # -------------------------------------------------------
    if "K-패스" in title:
        # 월 대중교통비 7만원 사용 시 20% 환급 -> 약 1.5만원
        return 15000
    if "천원의 아침밥" in title:
        # 1식 4000원짜리를 1000원에 이용 (3000원 이득) x 월 20일
        return 60000
    if "청년 맞춤형 요금제" in title:
        # 일반 요금제 대비 월 1만원 내외 절약 효과
        return 10000
    if "청년문화예술패스" in title:
        # 연 15만원 -> 월 약 1.25만원
        return 12500
    if "행복주택" in title:
        # 시세 대비 60~80% 임대료 -> 월세 약 15만원 절약 효과 가정
        return 150000
    if "청년마음건강지원사업" in title:
        # 바우처(서비스) 지원이므로 현금성 0원
        return 0

    # -------------------------------------------------------
    # [4] 진로 / 취업 (Career)
    # -------------------------------------------------------
    if "국민내일배움카드" in title:
        # 훈련장려금 월 최대 11.6만원
        return 116000
    if "면접 정장 무료 대여" in title:
        # 현물 지원 0원
        return 0
    if "청년 자격증 응시료 지원" in title:
        # 연 최대 10~30만원 -> 월 약 1~2만원
        return 15000
    if "청년일자리도약장려금" in title:
        # 청년 근속 인센티브 2년 최대 480만원 -> 월 20만원
        return 200000
    if "청년창업사관학교" in title:
        # 사업화 자금(법인/사업용)이므로 개인 자산 아님
        return 0
    if "국민취업지원제도" in title:
        # 구직촉진수당 월 50만원
        return 500000

    # -------------------------------------------------------
    # [5] 자산 형성 (Asset) - 매칭 지원금만 계산
    # -------------------------------------------------------
    if "청년 주택드림 청약통장" in title:
        # 금리 우대 효과 (현금 유입 아님)
        return 0
    if "청년내일저축계좌" in title:
        # 정부 매칭 월 10만원 (최소)
        return 100000
    if "중개형 ISA" in title:
        # 세제 혜택
        return 0
    if "청년형 소득공제 장기펀드" in title:
        # 세제 혜택
        return 0
    if "희망두배 청년통장" in title:
        # 서울시 매칭 월 15만원
        return 150000

    return 0

def calculate_relevance_score(policy: SupportPolicy, event_name: str) -> int:
    """
    사용자의 목표(event_name)와 정책 간의 연관성을 점수화합니다.
    점수가 높을수록 해당 상황에 추천될 확률이 높습니다.
    """
    score = 0
    title = policy.title or ""
    target_text = (policy.target or "") + title
    
    keywords = []
    if policy.keywords:
        try:
            keywords = json.loads(policy.keywords)
        except:
            keywords = []

    # 이벤트 이름 기반 키워드 매칭
    # [학생/학업 관련]
    if any(word in event_name for word in ["교환학생", "대학", "학비", "등록금", "공부", "학교", "노트북"]):
        if policy.category == SupportCategory.SCHOLARSHIP: score += 5
        if "대학생" in target_text: score += 3
        if "장학금" in keywords: score += 2

    # [취업/진로 관련]
    if any(word in event_name for word in ["취업", "면접", "자격증", "인턴", "일자리", "구직"]):
        if policy.category == SupportCategory.CAREER: score += 5
        if "구직" in target_text or "미취업" in target_text: score += 3
        if "취업" in keywords or "자격증" in keywords: score += 2

    # [주거/자취 관련]
    if any(word in event_name for word in ["자취", "독립", "월세", "보증금", "이사", "방 구하기"]):
        if "주거" in keywords or "월세" in keywords or "행복주택" in title: score += 5
        if policy.category == SupportCategory.LIVING: score += 1

    # [자산/목돈/여행 관련]
    if any(word in event_name for word in ["목돈", "여행", "자동차", "결혼", "투자", "1억"]):
        if policy.category == SupportCategory.ASSET: score += 5
        if "자산" in keywords or "적금" in keywords: score += 3
        # 단순 생활비 지원도 목돈 마련에 도움됨
        if policy.category == SupportCategory.LIVING: score += 2

    # 2. 범용성 높은 정책 가산점 (누구나 신청 쉬운 것)
    if "K-패스" in title or "청년 맞춤형 요금제" in title:
        score += 1
        
    # 3. 정책 대상 제한에 따른 필터링 (간단한 키워드 기반)
    # 예: '미취업' 대상인데 이벤트가 '직장인' 관련이면 감점 등은 생략하고 점수제로만 운영

    return score

def find_suitable_support(
    session: Session, 
    monthly_needed: int,
    event_name: str = ""
) -> Optional[Dict[str, Any]]:
    """
    DB에서 정책을 조회하고, 사용자 상황(event_name)에 가장 적합한 정책을 추천합니다.
    """
    if not session:
        return None

    # 전체 정책 조회
    policies = session.exec(select(SupportPolicy)).all()
    
    candidates = []
    
    for policy in policies:
        monthly_amount = estimate_policy_amount(policy)
        if monthly_amount <= 0:
            continue
            
        relevance_score = calculate_relevance_score(policy, event_name)
        
        # 필터링: 점수가 0이어도 금액이 필요 금액의 10% 이상이면 후보 포함
        if relevance_score == 0 and monthly_amount < monthly_needed * 0.1:
            continue
            
        candidates.append({
            "policy": policy,
            "monthly_amount": monthly_amount,
            "score": relevance_score
        })
    
    if not candidates:
        return None
        
    candidates.sort(key=lambda x: (x["score"], x["monthly_amount"]), reverse=True)
    
    best_match = candidates[0]
    policy = best_match["policy"]
    
    return {
        "id": policy.id,
        "name": policy.title,
        "monthly_amount": best_match["monthly_amount"],
        "period": policy.apply_period,
        "category": policy.category,
        "application_url": policy.application_url or "",
        "description": policy.subtitle or ""
    }

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

    saving_rate = DEFAULT_SAVING_RATE
    found_category = False

    for key, rate in CATEGORY_SAVING_RATES.items():
        if key in overspent_category:
            saving_rate = rate
            found_category = True
            break
    
    # 1. 절약 가능 금액 추정
    if category_amount > 0:
        # 해당 카테고리의 20% 절약 가정
        monthly_savings = int(category_amount * saving_rate)
    else:
        # 보수적 추정: 현재 저축액의 20% 추가 (전체 소비의 일부 절약)
        monthly_savings = int(monthly_save_potential * saving_rate) if monthly_save_potential > 0 else 50000
    
    # 2. 실제 월 저축액
    actual_monthly = monthly_save_potential + monthly_savings
    
    # 3. 실제로 모이는 금액
    final_estimated_asset = current_amount + (actual_monthly * period_months)
    
    # 4. 목표 대비 달성률
    achievement_rate = (final_estimated_asset / target_amount * 100) if target_amount > 0 else 0
    shortfall = max(0, target_amount - final_estimated_asset)
    expected_period = -1
    
    # 5. 실제 달성 기간
    if actual_monthly > 0:
        expected_period = calculate_achievement_months(
            target_amount, current_amount, actual_monthly
        )
    
    is_aggressive = False
    if achievement_rate < 50 and saving_rate < AGGRESSIVE_SAVING_RATE:
        saving_rate = AGGRESSIVE_SAVING_RATE
        is_aggressive = True
        
        if category_amount > 0:
            monthly_savings = int(category_amount * saving_rate)
        else:
            monthly_savings = int(monthly_save_potential * saving_rate) if monthly_save_potential > 0 else 70000
            
        actual_monthly = monthly_save_potential + monthly_savings
        final_estimated_asset = current_amount + (actual_monthly * period_months)
        achievement_rate = (final_estimated_asset / target_amount * 100) if target_amount > 0 else 0
        shortfall = max(0, target_amount - final_estimated_asset)
        
        if actual_monthly > 0:
            expected_period = calculate_achievement_months(
                target_amount, current_amount, actual_monthly
            )
    
    # 6. 추천 판단 (50% 이상이면 추천)
    is_recommended = (achievement_rate >= 50)
    
    tags = [f"월 {monthly_savings:,}원 절약"]
    if is_aggressive:
        tags.append("도전적 목표")
    elif achievement_rate >= 100:
        tags.append("목표 달성")
        tags.append("강력 추천")
    elif achievement_rate >= 80:
        tags.append("추천")
    elif achievement_rate >= 50:
        tags.append("절반 달성")
    
    return {
        "plan_type": "FRUGAL",
        "plan_title": "초절약 플랜",
        "description": f"{overspent_category} 지출을 {int(saving_rate*100)}% 줄여 월 {monthly_savings:,}원 추가 확보",
        "monthly_required": actual_monthly,
        "monthly_shortfall": max(0, shortfall // period_months) if period_months > 0 else 0,
        "final_estimated_asset": final_estimated_asset,
        "expected_period": expected_period,
        "is_recommended": is_recommended,
        "tags": tags,
        "recommendation": f"작은 절약으로 목표에 더 가까워질 수 있습니다.",
        "next_tool": "recommend_budget",
        "plan_detail": {
            "monthly_savings": monthly_savings,
            "achievement_rate": int(achievement_rate),
            "shortfall": shortfall,
            "target_categories": [overspent_category],
            "saving_rate_applied": saving_rate,
            "variant_id": "frugal_all_categories"
        }
    }


def generate_plan_support(
    session: Session,
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
    
    suitable_support = find_suitable_support(session, monthly_gap, event_name)
    
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
        tags.append(f"지원금 활용")
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
    session: Session,
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
            session,
            current_amount, target_amount, period_months, monthly_save_potential, event_name
        ),
        generate_plan_investment(
            current_amount, target_amount, period_months, monthly_save_potential
        )
    ]


def simulate_event(
    session: Session,
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
                session,
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