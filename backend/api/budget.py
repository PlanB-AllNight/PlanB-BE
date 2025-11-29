from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from backend.database import get_session
from backend.models.user import User
from backend.api.deps import get_current_user
from backend.models.budget import BudgetAnalysis
from backend.services.budget.recommend_budget_service import run_budget_recommendation_service

router = APIRouter()

# 맞춤 예산 추천 API
@router.post("/recommend")
async def generate_budget_recommendation(
    plan: str = Query(..., description="예산 규칙 (50/30/20 | 60/20/20 | 40/30/30)"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    try:
        result = await run_budget_recommendation_service(
            user=current_user,
            selected_plan=plan,
            session=session
        )

        return {
            "success": True,
            "data": result
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"예산 추천 생성 중 오류: {str(e)}"
        )

# 예산 추천 히스토리
@router.get("/history")
async def get_budget_history(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    try:
        statement = (
            select(BudgetAnalysis)
            .where(BudgetAnalysis.user_id == current_user.id)
            .order_by(BudgetAnalysis.created_at.desc())
            .limit(limit)
        )

        records = session.exec(statement).all()

        history = [
            {
                "id": r.id,
                "plan_type": r.plan_type,
                "essential_budget": r.essential_budget,
                "optional_budget": r.optional_budget,
                "saving_budget": r.saving_budget,
                "created_at": r.created_at.isoformat()
            }
            for r in records
        ]

        return {
            "success": True,
            "count": len(history),
            "data": history
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"예산 추천 기록 조회 중 오류: {str(e)}"
        )

# 예산안 상세 조회
@router.get("/{budget_id}")
async def get_budget_detail(
    budget_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    try:
        record = session.get(BudgetAnalysis, budget_id)

        if not record:
            raise HTTPException(status_code=404, detail="예산 추천 기록을 찾을 수 없습니다.")

        if record.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="권한이 없습니다.")

        return {
            "success": True,
            "data": {
                "id": record.id,
                "plan_type": record.plan_type,
                "essential_budget": record.essential_budget,
                "optional_budget": record.optional_budget,
                "saving_budget": record.saving_budget,
                "ai_proposal": record.ai_proposal,
                "category_proposals": record.category_proposals,
                "created_at": record.created_at.isoformat()
            }
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"예산 추천 상세 조회 중 오류: {str(e)}"
        )
