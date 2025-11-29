from backend.mcp.registry import mcp_registry
from backend.models.user import User
from sqlmodel import Session

from backend.services.simulate.simulate_event_service import create_challenge_with_plan

@mcp_registry.register(
    name="create_challenge",
    description="선택된 플랜으로 새로운 챌린지를 생성합니다."
)
async def create_challenge_tool(
    *,
    # MCP Agent에서 자동 주입
    user: User,
    session: Session,

    # ======= 프론트의 Payload와 정확히 동일한 필드 =======
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: int,
    challenge_name: str,

    plan_type: str,
    plan_title: str,
    description: str,
    monthly_required: int,
    monthly_shortfall: int,
    final_estimated_asset: int,
    expected_period: int,
    plan_detail: dict,
):
    """
    MCP Tool: 챌린지 생성
    """
    try:
        # 서비스에서 필요로 하는 selected_plan 형태로 재구성
        selected_plan = {
            "plan_type": plan_type,
            "plan_title": plan_title,
            "description": description,
            "monthly_required": monthly_required,
            "monthly_shortfall": monthly_shortfall,
            "final_estimated_asset": final_estimated_asset,
            "expected_period": expected_period,
            "plan_detail": plan_detail
        }

        result = await create_challenge_with_plan(
            user=user,
            event_name=event_name,
            target_amount=target_amount,
            period_months=period_months,
            current_amount=current_amount,
            selected_plan=selected_plan,
            challenge_name=challenge_name,
            session=session
        )

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        # MCP Tool Error 형식으로 반환
        return {
            "success": False,
            "error": str(e)
        }