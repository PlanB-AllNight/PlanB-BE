from fastapi import APIRouter, Depends
from sqlmodel import Session
from backend.core.security import get_session, get_current_user
from backend.models.user import User
from backend.mcp.models import MCPRequest, MCPResponse
from backend.mcp.agent_runner import run_mcp_agent

router = APIRouter(prefix="/mcp", tags=["MCP Agent"])

@router.post("/intent", response_model=MCPResponse)
async def endpoint_mcp_intent(
    req: MCPRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    MCP Agent 진입점
    - 버튼 클릭(Intent)을 받아 적절한 도구를 실행하고,
    - Agent의 판단 과정(Trace)을 포함하여 결과를 반환합니다.
    """
    result = await run_mcp_agent(
        req=req,   
        user=user,
        session=session
    )

    return MCPResponse(**result)