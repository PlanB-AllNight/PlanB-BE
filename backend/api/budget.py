from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from datetime import datetime

from backend.database import get_session
from backend.models.user import User
from backend.api.deps import get_current_user
from backend.models.budget import BudgetAnalysis, BudgetSummary, BudgetSummaryItem
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
                "title": r.title,
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
        
        plan_percents = {
            "50/30/20": (50, 30, 20),
            "60/20/20": (60, 20, 20),
            "40/40/20": (40, 40, 20),
        }

        needs_p, wants_p, savings_p = plan_percents.get(record.plan_type, (0, 0, 0))

        return {
            "success": True,
            "data": {
                "id": record.id,
                "spending_analysis_id": record.spending_analysis_id,
                "title": record.title,
                "date": record.created_at.strftime("%Y년 %m월"),
                "selected_plan": record.plan_type,
                "budget_summary": {
                    "needs": {"amount": record.essential_budget, "percent": needs_p},
                    "wants": {"amount": record.optional_budget, "percent": wants_p},
                    "savings": {"amount": record.saving_budget, "percent": savings_p},
                },
                "ai_proposal": record.ai_proposal,
                "category_proposals": record.category_proposals,
            }
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"예산 추천 상세 조회 중 오류: {str(e)}"
        )

@router.post("/recommend/save")
async def save_selected_budget(
    payload: dict,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    사용자가 선택한 예산안(추천 결과)을 BudgetAnalysis 테이블에 저장하는 API
    """

    try:
        # 예산 구조 추출
        spending_analysis_id=payload.get("spending_analysis_id")
        title=payload.get("title")
        plan_type = payload.get("plan_type")
        essential_budget = payload.get("essential_budget")
        optional_budget = payload.get("optional_budget")
        saving_budget = payload.get("saving_budget")

        category_proposals = payload.get("category_proposals")
        ai_proposal = payload.get("ai_proposal")

        if not (plan_type and essential_budget and optional_budget and saving_budget):
            raise HTTPException(400, "필수 예산 정보가 누락되었습니다.")
        
        # 동일한 분석 결과 & 동일한 플랜이면 중복으로 판단
        existing = session.exec(
            select(BudgetAnalysis)
            .where(BudgetAnalysis.user_id == current_user.id)
            .where(BudgetAnalysis.spending_analysis_id == spending_analysis_id)
            .where(BudgetAnalysis.plan_type == plan_type)
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="이미 동일한 분석 결과와 동일한 플랜의 예산안이 저장되어 있습니다."
            )

        # DB 저장
        new_obj = BudgetAnalysis(
            user_id=current_user.id,
            spending_analysis_id=spending_analysis_id,

            title=title,
            plan_type=plan_type,
            essential_budget=essential_budget,
            optional_budget=optional_budget,
            saving_budget=saving_budget,

            category_proposals=category_proposals,
            ai_proposal=ai_proposal,
            created_at=datetime.now()
        )

        session.add(new_obj)
        session.commit()
        session.refresh(new_obj)

        return {
            "success": True,
            "message": "예산안이 저장되었습니다.",
            "budget_id": new_obj.id
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"예산안 저장 중 오류: {str(e)}"
        )