from backend.mcp.registry.mcp_registry_finance import mcp_registry_finance
from backend.models.user import User
from sqlmodel import Session
from typing import Any, Optional

from backend.services.simulate.simulate_event_service import run_challenge_simulation_service

@mcp_registry_finance.register(
    name="simulate_event",
    description="목표 금액, 기간, 이벤트 이름을 기반으로 맞춤형 플랜을 시뮬레이션합니다."
)
async def simulate_event_tool(
    *,
    # MCP Agent가 주입하는 값
    user: User,
    session: Session,

    # LLM이 전달하는 값 (payload + arguments)
    event_name: str,
    target_amount: int,
    period: int,
    current_asset: Optional[int] = None,
    monthly_save_potential: Optional[int] = None
) -> Any:
    """
    MCP Tool: 이벤트 시뮬레이션 실행
    """

    try:
        return await run_challenge_simulation_service(
            user=user,
            event_name=event_name,
            target_amount=target_amount,
            period_months=period,
            current_amount=current_asset,
            monthly_save_potential=monthly_save_potential,
            session=session
        )

    except Exception as e:
        raise RuntimeError(f"시뮬레이션 중 오류: {str(e)}")


