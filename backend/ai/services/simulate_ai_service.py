import json

from typing import Dict, Any, List, Optional
from sqlmodel import Session, select

from backend.models.analyze_spending import SpendingAnalysis, SpendingCategoryStats
from backend.services.simulate.simulate_event import (
    analyze_situation,
    generate_plan_maintain,
    generate_plan_frugal,
    generate_plan_support,
    generate_plan_investment
)

from backend.ai.prompts.simulate_prompt import format_simulate_prompt
from backend.ai.client import generate_json


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

    prompt = format_simulate_prompt(
        user_name,
        event_name,
        target_amount,
        period_months,
        current_amount,
        tool_plans_for_ai
    )

    try:
        response = generate_json("JSON으로 답변하세요", prompt)
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