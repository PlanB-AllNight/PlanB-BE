from sqlmodel import Session
from backend.mcp.registry import mcp_registry

from backend.models.user import User
from backend.services.recommend_budget_service import run_budget_recommendation_service

@mcp_registry.register(
    name="recommend_budget",
    description="최근 소비 분석 결과를 기반으로 맞춤 예산안을 생성합니다. 입력값: plan_type (50/30/20, 60/20/20, 40/30/30)"
)
async def recommend_budget(
    user: User,
    session: Session,
    plan_type: str = "50/30/20",   # 기본값 적용
    **kwargs
) -> dict:
    """
    [MCP Tool] 사용자 맞춤 예산 생성
    """

    allowed = ["50/30/20", "60/20/20", "40/30/30"]
    if plan_type not in allowed:
        plan_type = "50/30/20"   # 자동 fallback

    try:
        result = await run_budget_recommendation_service(
            user=user,
            selected_plan=plan_type,
            session=session
        )
        return {
            "status": "success",
            "message": f"'{plan_type}' 규칙으로 예산 추천을 완료했습니다.",
            "data": result.dict()
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "data": None
        }