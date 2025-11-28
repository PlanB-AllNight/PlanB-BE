import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from fastapi import HTTPException
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from backend.models.user import User
from backend.models.analyze_spending import SpendingAnalysis
from backend.models.challenge import Challenge, ChallengeStatus, PlanType
from backend.tools.simulate_event import (
    analyze_situation,
    generate_plan_maintain,
    generate_plan_frugal,
    generate_plan_support,
    generate_plan_investment
)
from backend.tools.analyze_spending import get_current_asset

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_latest_analysis(user_id: int, session: Session) -> Optional[SpendingAnalysis]:
    """사용자의 가장 최근 소비분석 조회"""
    try:
        statement = select(SpendingAnalysis).where(
            SpendingAnalysis.user_id == user_id
        ).order_by(SpendingAnalysis.created_at.desc())
        
        return session.exec(statement).first()
    except Exception as e:
        print(f"최신 소비분석 조회 실패: {e}")
        return None


def generate_comprehensive_plans(
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: int,
    monthly_save_potential: int,
    user_name: str,
    latest_analysis: Optional[SpendingAnalysis] = None
) -> Dict[str, Any]:
    """
    플랜 생성 전략:
    - MAINTAIN: 1개 (기준점)
    - FRUGAL: 1~4개 (절약 대상 카테고리에 따라 여러 변형)
    - SUPPORT: 0~1개 (지원금 찾으면 생성)
    - INVESTMENT: 0~2개 (STO 상품 개수만큼)
    → 총 2~8개 플랜 생성 가능
    
    Tool 메타 정보를 보존 이유
    - sto_product: 투자 플랜에서 어떤 STO 상품인지 정보
    - support_info: 지원금 플랜에서 어떤 장학금/지원금인지 정보
    - investment_profit: 투자 수익 예상 금액
    - next_tool: 다음에 실행할 Tool (예: "recommend_budget")
    - 이 정보들은 프론트엔드에서 상세 정보 표시에 필요함
    """
    #  Tool의 정밀 상황 분석
    situation = analyze_situation(
        current_amount=current_amount,
        target_amount=target_amount,
        period_months=period_months,
        monthly_save_potential=monthly_save_potential
    )
    
    base_plans = {
        "MAINTAIN": generate_plan_maintain(
            current_amount, target_amount, period_months, monthly_save_potential
        ),
        "FRUGAL": generate_plan_frugal(
            current_amount, target_amount, period_months, monthly_save_potential
        ),
        "SUPPORT": generate_plan_support(
            current_amount, target_amount, period_months, 
            monthly_save_potential, event_name
        ),
        "INVESTMENT": generate_plan_investment(
            current_amount, target_amount, period_months, monthly_save_potential
        )
    }
    
    tool_plans_for_ai = []
    for p_type, plan in base_plans.items():
        tool_plans_for_ai.append({
            "plan_type": p_type,
            "monthly_required": plan["monthly_required"],
            "monthly_shortfall": plan["monthly_shortfall"],
            "expected_period": plan["expected_period"],
            "is_recommended_by_tool": plan["is_recommended"],
            "tool_message": plan["recommendation"],
            "support_found": plan.get("support_info") is not None if p_type == "SUPPORT" else None,
            "sto_product": plan.get("sto_product", {}).get("name") if p_type == "INVESTMENT" else None
        })
    
    #  소비분석 컨텍스트 구성
    spending_context = ""
    overspent_category = "알 수 없음"
    
    if latest_analysis:
        overspent_category = latest_analysis.overspent_category
        spending_context = f"""
## 최근 소비 패턴 (참고)
- 주요 지출: {latest_analysis.top_category}
- 과소비 항목: {overspent_category} ← 절약 플랜 제안 시 이 항목을 줄이는 것을 구체적으로 언급할 것
"""
    
    #  AI 프롬프트 구성 (다양한 플랜 생성 허용)
    prompt = f"""
당신은 대학생을 위한 창의적인 금융 코치 'PlanB'입니다.
사용자({user_name})가 '{event_name}' 목표를 세웠습니다.

## 목표 정보
- 금액: {target_amount:,}원
- 기간: {period_months}개월
- 현재 자산: {current_amount:,}원

## Tool 분석 결과
- 난이도: {situation['difficulty']}
- 부족 금액: {situation['shortfall_amount']:,}원
- 추가 월 저축 필요: {situation['monthly_gap']:,}원

{spending_context}

## Tool이 계산한 플랜 후보 (금액/기간은 정확함)
{json.dumps(tool_plans_for_ai, ensure_ascii=False, indent=2)}

## 당신의 임무
1. **다양한 플랜 생성**: 위 4개 타입을 기반으로 **총 3~8개의 플랜**을 만드세요.
   - **같은 타입(예: FRUGAL)도 여러 개 생성 가능합니다!**
   - 예: FRUGAL 타입이지만
     * "카페만 절약" 플랜
     * "배달음식만 절약" 플랜  
     * "카페+배달음식 모두 절약" 플랜
   
2. 난이도별 플랜 개수 가이드:
   - 난이도 '쉬움': 3~4개 (MAINTAIN + FRUGAL 변형들)
   - 난이도 '보통': 4~5개 (MAINTAIN + FRUGAL 변형들 + SUPPORT)
   - 난이도 '어려움': 5~7개 (MAINTAIN + FRUGAL 변형들 + SUPPORT + INVESTMENT)
   - 난이도 '매우 어려움': 6~8개 (모든 타입 + 여러 변형)
   - **MAINTAIN은 필수 1개 포함**

3. FRUGAL 플랜 변형 아이디어:
   - 과소비 항목('{overspent_category}')을 집중 절약
   - 다른 카테고리(배달음식, 사회/모임 등)를 집중 절약
   - 여러 카테고리를 동시에 절약
   - 절약 강도를 다르게 (10% vs 20%)

4. 각 플랜마다 다른 **plan_title**, **description**, **recommendation**, **tags**를 작성하세요.

5. **is_recommended**는 상황에 맞게 True/False로 지정하세요 (추천 플랜은 3~4개 정도).

6. **중요**: 금액/기간 데이터는 절대 작성하지 마세요. Tool 값을 사용합니다.

## 응답 형식 (JSON만)
{{
    "ai_summary": "전체 상황 요약 (100-150자, 존댓말, 난이도 언급)",
    "recommendation": "최종 조언 (80-120자, 존댓말, 가장 추천하는 플랜 1개 명시)",
    "plans": [
        {{
            "plan_type": "MAINTAIN",
            "plan_title": "현재 속도로 {event_name} 준비",
            "description": "...",
            "recommendation": "...",
            "tags": ["안정적", "장기"],
            "is_recommended": false,
            "variant_id": "maintain_baseline"
        }},
        {{
            "plan_type": "FRUGAL",
            "plan_title": "카페만 집중 절약",
            "description": "카페 지출만 20% 줄이면...",
            "recommendation": "...",
            "tags": ["카페절약", "현실적"],
            "is_recommended": true,
            "variant_id": "frugal_cafe_only"
        }},
        {{
            "plan_type": "FRUGAL",
            "plan_title": "배달음식 줄이기",
            "description": "배달음식을 주 1회로 제한하면...",
            "recommendation": "...",
            "tags": ["배달절약", "건강"],
            "is_recommended": true,
            "variant_id": "frugal_delivery_only"
        }},
        {{
            "plan_type": "FRUGAL",
            "plan_title": "전방위 초절약",
            "description": "카페+배달음식+쇼핑 모두 10% 줄이면...",
            "recommendation": "...",
            "tags": ["고강도", "빠른달성"],
            "is_recommended": false,
            "variant_id": "frugal_all_categories"
        }}
    ]
}}

**핵심:**
- 같은 plan_type도 여러 개 생성 가능! (variant_id로 구분)
- 각 플랜은 서로 다른 전략과 메시지
- 총 3~8개 생성 (난이도에 따라)
- 추천 플랜은 3~4개 정도
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": "당신은 PlanB 금융 코치입니다. 창의적이고 다양한 플랜을 생성하되, JSON 형식으로만 응답하며 존댓말을 사용합니다."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,  # 창의성 높임
            max_tokens=3000,  # 여러 플랜 생성 위해 늘림
            response_format={"type": "json_object"}
        )
        
        ai_text = response.choices[0].message.content.strip()
        ai_result = json.loads(ai_text)
        
        #  AI 텍스트 + Tool 숫자 병합
        final_plans = []
        
        for ai_plan in ai_result.get("plans", []):
            p_type = ai_plan.get("plan_type", "").upper()
            variant_id = ai_plan.get("variant_id", "default")
            
            # Tool이 계산한 원본 플랜 가져오기
            base_plan = base_plans.get(p_type)
            
            if base_plan:
                # AI의 창의적 텍스트 사용
                merged_plan = {
                    "plan_type": p_type,
                    "plan_title": ai_plan.get("plan_title", base_plan["plan_title"]),
                    "description": ai_plan.get("description", base_plan["description"]),
                    "recommendation": ai_plan.get("recommendation", base_plan["recommendation"]),
                    "tags": ai_plan.get("tags", base_plan.get("tags", [])),
                    "is_recommended": ai_plan.get("is_recommended", base_plan["is_recommended"]),
                    "variant_id": variant_id,  # 변형 구분용
                }
                
                # Tool의 정확한 수치 데이터로 강제 덮어쓰기
                merged_plan.update({
                    "monthly_required": base_plan["monthly_required"],
                    "monthly_shortfall": base_plan["monthly_shortfall"],
                    "final_estimated_asset": base_plan["final_estimated_asset"],
                    "expected_period": base_plan["expected_period"],
                })
                
                # Tool의 추가 메타 정보 보존
                merged_plan["plan_detail"] = base_plan.get("plan_detail", {})
                merged_plan["plan_detail"]["variant_id"] = variant_id  # 변형 ID 추가
                
                if "sto_product" in base_plan:
                    merged_plan["sto_product"] = base_plan["sto_product"]
                if "support_info" in base_plan:
                    merged_plan["support_info"] = base_plan["support_info"]
                if "investment_profit" in base_plan:
                    merged_plan["investment_profit"] = base_plan["investment_profit"]
                if "monthly_saved" in base_plan:
                    merged_plan["monthly_saved"] = base_plan["monthly_saved"]
                if "next_tool" in base_plan:
                    merged_plan["next_tool"] = base_plan["next_tool"]
                
                final_plans.append(merged_plan)
                print(f"      → {p_type} ({variant_id}) 플랜 병합 완료")

        if not final_plans:
            raise ValueError("AI가 유효한 플랜을 반환하지 않음")

        return {
            "situation_analysis": situation,
            "plans": final_plans,
            "ai_summary": ai_result.get("ai_summary", ""),
            "recommendation": ai_result.get("recommendation", "")
        }

    except json.JSONDecodeError as e:
        print(f"    AI 응답 JSON 파싱 실패: {e}")
        print(f"      → 원본 응답: {ai_text[:200]}...")
        
    except Exception as e:
        print(f"    AI 생성 실패: {e}")
    
    # ========================================
    # 폴백: AI 실패 시 Tool 기본값 반환
    # ========================================
    print(f"\n    AI 생성 실패 - Tool 기본 플랜 사용 (폴백)")
    
    fallback_plans = [base_plans["MAINTAIN"]]
    
    if situation.get('plan_suitability', {}).get('FRUGAL', False):
        fallback_plans.append(base_plans["FRUGAL"])
    if situation.get('plan_suitability', {}).get('SUPPORT', False):
        fallback_plans.append(base_plans["SUPPORT"])
    if situation.get('plan_suitability', {}).get('INVESTMENT', False):
        fallback_plans.append(base_plans["INVESTMENT"])
    
    print(f"      → 폴백 플랜: {[p['plan_type'] for p in fallback_plans]}")
    print(f"{'='*80}\n")
    
    return {
        "situation_analysis": situation,
        "plans": fallback_plans,
        "ai_summary": f"{user_name}님의 '{event_name}' 목표 달성을 위해 {len(fallback_plans)}가지 플랜을 준비했습니다.",
        "recommendation": "각 플랜을 확인하시고 본인에게 가장 적합한 방법을 선택해보세요."
    }


async def run_challenge_simulation_service(
    user: User,
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: Optional[int],
    monthly_save_potential: Optional[int],
    session: Session
) -> Dict[str, Any]:
    """
    챌린지 시뮬레이션 통합 서비스
    
    프로세스:
    1. 현재 자산 조회 (입력 없으면 자동)
    2. 월 저축 가능액 조회 (입력 없으면 최신 분석에서)
    3. AI 플랜 생성 (generate_comprehensive_plans 호출)
    4. 결과 반환 (DB 저장은 create_challenge API에서)
    """
    
    #  현재 자산 조회
    if current_amount is None:
        current_amount = get_current_asset(user.id) or 0
        print(f"   - 현재 자산: {current_amount:,}원 (자동 조회)")
    else:
        print(f"   - 현재 자산: {current_amount:,}원 (사용자 입력)")
        
    #  월 저축 가능액 조회
    latest_analysis = None
    if monthly_save_potential is None:
        latest_analysis = get_latest_analysis(user.id, session)
        monthly_save_potential = max(0, latest_analysis.save_potential) if latest_analysis else 0
    else:
        latest_analysis = get_latest_analysis(user.id, session)

    #  AI 플랜 생성 서비스 호출
    result = generate_comprehensive_plans(
        event_name=event_name,
        target_amount=target_amount,
        period_months=period_months,
        current_amount=current_amount,
        monthly_save_potential=monthly_save_potential,
        user_name=user.name,
        latest_analysis=latest_analysis
    )
    
    response_data = {
        "event_name": event_name,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "shortfall_amount": max(0, target_amount - current_amount),
        "period_months": period_months,
        "monthly_save_potential": monthly_save_potential,
        
        # generate_comprehensive_plans 결과
        "situation_analysis": result["situation_analysis"],
        "plans": result["plans"],
        "ai_summary": result["ai_summary"],
        "recommendation": result["recommendation"],
        
        "simulation_date": datetime.now().strftime("%Y-%m-%d"),
        "meta": {
            "plans_count": len(result["plans"]),
            "recommended_plans": [p["plan_type"] for p in result["plans"] if p["is_recommended"]],
            "has_latest_analysis": latest_analysis is not None
        }
    }
    
    return response_data


async def create_challenge_with_plan(
    user: User,
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: int,
    selected_plan: Dict[str, Any],
    session: Session
) -> Dict[str, Any]:
    """
    선택한 플랜으로 챌린지 생성
    """
    
    #  중복 체크 (같은 이벤트로 진행 중인 챌린지)
    statement = select(Challenge).where(
        Challenge.user_id == user.id,
        Challenge.event_name == event_name,
        Challenge.status == ChallengeStatus.IN_PROGRESS
    )
    existing = session.exec(statement).first()
    
    if existing:
        return {
            "id": existing.id,
            "event_name": existing.event_name,
            "plan_title": existing.plan_title,
            "status": existing.status.value,
            "start_date": existing.start_date,
            "end_date": existing.end_date,
            "message": "이미 진행 중인 챌린지가 있습니다.",
            "is_new": False
        }

    latest_analysis = get_latest_analysis(user.id, session)
    
    today = date.today()
    end_date = today + relativedelta(months=period_months)
    
    new_challenge = Challenge(
        user_id=user.id,
        spending_analysis_id=latest_analysis.id if latest_analysis else None,
        
        event_name=event_name,
        current_amount=current_amount,
        target_amount=target_amount,
        shortfall_amount=target_amount - current_amount,
        period_months=period_months,
        
        plan_type=PlanType(selected_plan['plan_type']),
        plan_title=selected_plan['plan_title'],
        description=selected_plan['description'],
        monthly_required=selected_plan['monthly_required'],
        monthly_shortfall=selected_plan['monthly_shortfall'],
        final_estimated_asset=selected_plan['final_estimated_asset'],
        expected_period=selected_plan['expected_period'],
        plan_detail=selected_plan.get('plan_detail', {}),
        
        status=ChallengeStatus.IN_PROGRESS,
        start_date=today,
        end_date=end_date
    )
    
    try:
        session.add(new_challenge)
        session.commit()
        session.refresh(new_challenge)
        
        return {
            "id": new_challenge.id,
            "event_name": new_challenge.event_name,
            "plan_title": new_challenge.plan_title,
            "status": new_challenge.status.value,
            "start_date": new_challenge.start_date,
            "end_date": new_challenge.end_date,
            "message": f"'{event_name}' 챌린지가 시작되었습니다!",
            "is_new": True
        }
        
    except Exception as e:
        session.rollback()
        print(f"    DB 저장 실패: {e}")
        print(f"{'='*80}\n")
        raise HTTPException(status_code=500, detail=f"챌린지 생성 실패: {str(e)}")