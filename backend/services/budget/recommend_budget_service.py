from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from backend.models.user import User
from backend.models.budget import BudgetAnalysis, BudgetResponse, BudgetSummaryItem, BudgetSummary, CategoryBudget
from backend.models.analyze_spending import SpendingAnalysis

from backend.services.budget.recommend_budget import recommend_budget_logic

from backend.ai.services.budget_ai_service import generate_ai_insight

# BudgetAnalysis 테이블에 저장할 데이터 변환
def convert_to_budget_analysis_format(baseline, ai_output):
    essential = baseline["summary"]["needs"]["amount"]
    optional = baseline["summary"]["wants"]["amount"]
    saving = baseline["summary"]["savings"]["amount"]

    ai_proposal_list = [
        ai_output["ai_insight"]["sub_text"],
        ai_output["ai_insight"]["main_suggestion"],
        ai_output["ai_insight"]["expected_effect"]
    ]

    # extra_suggestion이 존재하고 None/빈값이 아닐 때만 추가
    extra = ai_output["ai_insight"].get("extra_suggestion")
    if extra and isinstance(extra, str) and extra.strip():
        ai_proposal_list.append(extra)
    
    # adjustment_info가 존재하고 None/빈값이 아닐 때만 추가
    adjust = ai_output["ai_insight"].get("adjustment_info")
    if adjust and isinstance(adjust, str) and adjust.strip():
        ai_proposal_list.append(adjust)

    # ai_output["categories"]가 이제 그룹별 딕셔너리 구조
    grouped_categories = ai_output["categories"]
    
    return {
        "essential_budget": essential,
        "optional_budget": optional,
        "saving_budget": saving,
        "category_proposals": grouped_categories,  # 그룹별 구조
        "ai_proposal": ai_proposal_list
    }

async def run_budget_recommendation_service(
    user: User,
    selected_plan: str,
    session: Session
):
    print(f"[{user.name}] 맞춤 예산 생성 시작…")

    # 1. 최근 소비 분석 ID 찾기
    recent_analysis = session.exec(
        select(SpendingAnalysis)
        .where(SpendingAnalysis.user_id == user.id)
        .order_by(SpendingAnalysis.id.desc())
    ).first()

    if not recent_analysis:
        raise HTTPException(status_code=404, detail="먼저 소비 분석을 진행해주세요.")

    spending_analysis_id = recent_analysis.id

    # 2. Tool 호출 (가장 첫 단계)
    baseline = recommend_budget_logic(
        user_id=user.id,
        selected_plan=selected_plan,
        recent_analysis=recent_analysis,
        session=session
    )

    ai_output = generate_ai_insight(baseline)

    # 7. BudgetAnalysis 저장 형태로 변환
    final_data = convert_to_budget_analysis_format(baseline, ai_output)

    created_at = datetime.now()

    # 8. DB 저장
    db_obj = BudgetAnalysis(
        user_id=user.id,
        spending_analysis_id=spending_analysis_id,
        title=ai_output["title"],
        plan_type=selected_plan,

        essential_budget=final_data["essential_budget"],
        optional_budget=final_data["optional_budget"],
        saving_budget=final_data["saving_budget"],

        category_proposals=final_data["category_proposals"],
        ai_proposal=final_data["ai_proposal"],

        created_at=created_at
    )

    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)

    print(f"🎉 BudgetAnalysis 저장 완료 (ID: {db_obj.id})")

    response = BudgetResponse(
        title=ai_output["title"],
        date=created_at.strftime("%Y-%m"),
        total_income=baseline["total_income"],
        selected_plan=baseline["selected_plan"],
        budget_summary=BudgetSummary(
            needs=BudgetSummaryItem(**baseline["summary"]["needs"]),
            wants=BudgetSummaryItem(**baseline["summary"]["wants"]),
            savings=BudgetSummaryItem(**baseline["summary"]["savings"])
        ),
        category_proposals={
            "needs": [CategoryBudget(**item) for item in baseline["recommended_budget"]["needs"]],
            "wants": [CategoryBudget(**item) for item in baseline["recommended_budget"]["wants"]],
            "savings": [CategoryBudget(**item) for item in baseline["recommended_budget"]["savings"]],
        },
        ai_proposal=final_data["ai_proposal"]
    )

    # 7. 프론트 응답
    return response