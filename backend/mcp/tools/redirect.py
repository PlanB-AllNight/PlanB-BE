from backend.mcp.registry import mcp_registry
from backend.models.user import User
from sqlmodel import Session

# Tool 등록
@mcp_registry.register(
    name="redirect",
    description="앱의 특정 페이지로 이동합니다."
)
async def redirect_tool(
    *,
    user: User,
    session: Session,
    target: str,      # e.g. "analysis", "budget", "challenge", "simulate"
):
    """
    MCP Redirect Tool
    프론트엔드가 페이지 이동에 사용할 정보를 반환.
    """

    # target → 실제 URL 매핑
    PAGE_MAP = {
        "analysis": "/analysis",
        "budget": "/budget",
        "simulate": "/simulate",
    }

    if target not in PAGE_MAP:
        return {
            "success": False,
            "error": f"존재하지 않는 redirect target: {target}"
        }

    return {
        "success": True,
        "target": target,
        "url": PAGE_MAP[target],
        "message": f"페이지 이동: {target}"
    }