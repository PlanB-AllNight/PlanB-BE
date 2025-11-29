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
from backend.models.analyze_spending import SpendingAnalysis, SpendingCategoryStats
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
    latest_analysis: Optional[SpendingAnalysis] = None,
    session: Optional[Session] = None
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
    #  상황 분석
    situation = analyze_situation(
        current_amount=current_amount,
        target_amount=target_amount,
        period_months=period_months,
        monthly_save_potential=monthly_save_potential
    )

    #  기본 플랜 리스트 생성
    base_plans_list = []

    # [MAINTAIN] 현상 유지 플랜 (항상 포함)
    base_plans_list.append(generate_plan_maintain(
        current_amount, target_amount, period_months, monthly_save_potential
    ))

    # [FRUGAL] 데이터 기반 절약 플랜 생성
    frugal_candidates = []
    
    if latest_analysis and session:
        # 상위 지출 카테고리 조회 (Wants 위주, 금액 큰 순서)
        # 실제로는 CATEGORY_MAP 등을 활용해 Needs(주거/통신)는 제외하는 것이 좋으나
        # 여기서는 금액이 큰 상위 3개를 가져와서 시뮬레이션
        try:
            stats = session.exec(
                select(SpendingCategoryStats)
                .where(SpendingCategoryStats.analysis_id == latest_analysis.id)
                .order_by(SpendingCategoryStats.amount.desc())
                .limit(3) 
            ).all()

            for stat in stats:
                # 카테고리별 절약 플랜 생성
                plan = generate_plan_frugal(
                    current_amount, target_amount, period_months, monthly_save_potential,
                    overspent_category=stat.category_name,
                    category_amount=stat.amount
                )
                plan["variant_id"] = f"frugal_{stat.category_name}"
                frugal_candidates.append(plan)
                
        except Exception as e:
            print(f"카테고리별 절약 플랜 생성 중 오류: {e}")

    # 데이터가 없거나 부족할 경우를 대비해 '기본 초절약 플랜' 하나 추가
    if not frugal_candidates:
        default_frugal = generate_plan_frugal(
            current_amount, target_amount, period_months, monthly_save_potential,
            overspent_category="불필요한 소비",
            category_amount=0 
        )
        default_frugal["variant_id"] = "frugal_default"
        frugal_candidates.append(default_frugal)
    
    base_plans_list.extend(frugal_candidates)

    # [SUPPORT] 지원금 플랜
    base_plans_list.append(generate_plan_support(
        session,
        current_amount, target_amount, period_months, 
        monthly_save_potential, event_name
    ))

    # [INVESTMENT] 투자 플랜
    base_plans_list.append(generate_plan_investment(
        current_amount, target_amount, period_months, monthly_save_potential
    ))

    # 모든 플랜이 비추천(False)이라면, 가장 효과가 좋은 상위 2개 플랜을 추천으로 변경
    if not any(p["is_recommended"] for p in base_plans_list):
        # MAINTAIN(현상유지)을 제외하고, 최종 자산이 가장 많은 플랜 찾기
        candidates = [p for p in base_plans_list if p["plan_type"] != "MAINTAIN"]
        
        if candidates:
            sorted_candidates = sorted(candidates, key=lambda x: x["final_estimated_asset"], reverse=True)
            top_plans = sorted_candidates[:2]
            
            for index, plan in enumerate(top_plans):
                plan["is_recommended"] = True
                
                tag_text = "최선의 선택" if index == 0 else "차선책"
                
                if isinstance(plan.get("tags"), list):
                    plan["tags"].insert(0, tag_text)
                else:
                    plan["tags"] = [tag_text]
                
                if index == 0:
                    plan["recommendation"] += " (현재 상황에서 가장 효과적인 방법입니다.)"
                else:
                    plan["recommendation"] += " (이 방법도 좋은 대안이 될 수 있습니다.)"

    #  AI에게 전달할 데이터 구성
    tool_plans_for_ai = []
    for plan in base_plans_list:
        tool_plans_for_ai.append({
            "variant_id": plan.get("variant_id", plan["plan_type"]),
            "plan_type": plan["plan_type"],
            "plan_title": plan["plan_title"],
            "monthly_required": plan["monthly_required"],
            "monthly_shortfall": plan["monthly_shortfall"],
            "final_estimated_asset": plan["final_estimated_asset"],
            "tool_message": plan["description"],
            "is_recommended": plan["is_recommended"]
        })

    #  AI 프롬프트 (Tool이 준 데이터를 그대로 활용하도록 유도)
    prompt = f"""
당신은 대학생을 위한 금융 코치 'PlanB'입니다.
사용자({user_name})의 목표('{event_name}') 달성을 위한 시뮬레이션 결과를 보고, 사용자에게 보여줄 플랜 카드를 완성해주세요.

## 목표 정보
- 금액: {target_amount:,}원
- 기간: {period_months}개월
- 현재 자산: {current_amount:,}원

## Tool이 계산한 플랜 후보들 (이 데이터를 기반으로 작성)
{json.dumps(tool_plans_for_ai, ensure_ascii=False, indent=2)}

## 임무
1. 위 'Tool이 계산한 플랜 후보들'을 **하나도 빠짐없이** 모두 포함하여 JSON으로 반환하세요.
2. 각 플랜의 **`plan_title`**, **`description`**, **`recommendation`**을 더 매력적이고 자연스러운 한국어(존댓말)로 다듬어주세요.
   - 예: "식비 절약 플랜" -> "배달 줄이고 집밥 먹기" 
   - 예: "식비 20% 절약 시..." -> "식비를 20%만 줄여도 목표에 한 걸음 더 가까워집니다."
3. **`tags`**는 해당 플랜의 핵심 특징(절약 금액, 감축 비율, 추천 여부 등)을 잘 나타내는 키워드로 **2~3개**를 생성해주세요.
   - `tool_tags`를 참고하되, 더 직관적인 단어로 변경해도 좋습니다.
   - 예: ["월 10만원 SAVE", "커피값 줄이기", "강력 추천"]
4. **중요**: 금액(`monthly_required`, `final_estimated_asset` 등)과 기간은 **절대 수정하지 말고** 입력받은 그대로 반환하세요. (계산은 Tool이 정확함)
5. `variant_id`는 입력받은 값을 그대로 유지하세요.

## 응답 형식 (JSON)
{{
    "ai_summary": "전체 분석 요약 (한 줄평)",
    "recommendation": "최종 조언",
    "plans": [
        {{
            "variant_id": "입력받은 variant_id 그대로",
            "plan_type": "...",
            "plan_title": "AI가 다듬은 제목",
            "description": "AI가 다듬은 설명",
            "recommendation": "AI가 쓴 추천/비추천 멘트",
            "tags": ["태그1", "태그2"],
            "is_recommended": true/false (Tool 값 참고하되 조정 가능)
        }},
        ...
    ]
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "JSON 형식으로만 응답하세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        ai_result = json.loads(response.choices[0].message.content.strip())
        
        #  AI 결과와 Tool 원본 데이터 병합
        final_plans = []
        
        # AI가 반환한 플랜 리스트를 순회하며 원본 데이터와 매칭
        ai_plans_map = {p.get("variant_id"): p for p in ai_result.get("plans", [])}
        
        for base_plan in base_plans_list:
            v_id = base_plan.get("variant_id", base_plan["plan_type"])
            ai_plan = ai_plans_map.get(v_id)
            
            if ai_plan:
                base_plan["plan_title"] = ai_plan.get("plan_title", base_plan["plan_title"])
                base_plan["description"] = ai_plan.get("description", base_plan["description"])
                base_plan["recommendation"] = ai_plan.get("recommendation", base_plan["recommendation"])
                base_plan["tags"] = ai_plan.get("tags", base_plan["tags"])
                
                if "is_recommended" in ai_plan:
                    base_plan["is_recommended"] = ai_plan["is_recommended"]
            
            final_plans.append(base_plan)

        return {
            "situation_analysis": situation,
            "plans": final_plans,
            "ai_summary": ai_result.get("ai_summary", ""),
            "recommendation": ai_result.get("recommendation", "")
        }

    except Exception as e:
        print(f"AI 생성 실패: {e}")
        return {
            "situation_analysis": situation,
            "plans": base_plans_list,
            "ai_summary": "AI 분석을 불러올 수 없어 기본 플랜을 표시합니다.",
            "recommendation": "플랜을 직접 확인해보세요."
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
        latest_analysis=latest_analysis,
        session=session
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
    challenge_name: Optional[str],
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
    
    # challenge_name 자동 생성
    if not challenge_name:
        if current_amount == 0:
            challenge_name = f"0원에서 {event_name} 도전"
        else:
            challenge_name = f"{current_amount:,}원에서 {event_name} 도전"

    latest_analysis = get_latest_analysis(user.id, session)
    
    today = date.today()
    end_date = today + relativedelta(months=period_months)
    
    new_challenge = Challenge(
        user_id=user.id,
        spending_analysis_id=latest_analysis.id if latest_analysis else None,
        
        challenge_name=challenge_name,
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