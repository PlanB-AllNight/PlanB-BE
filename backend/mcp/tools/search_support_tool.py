from backend.mcp.registry.mcp_registry_chat import mcp_registry_chat
from typing import Any, Dict, List, Optional

from sqlmodel import Session

from backend.models.user import User
from backend.services.support.search_support import (
    search_support_policies_ranked,
    calculate_age_from_birth
)


@mcp_registry_chat.register(
    name="search_support",
    description="장학금, 월세지원, 취업지원 등 사용자의 상황에 맞는 지원 정책을 검색합니다."
)
async def search_support_policy_tool(
    *,
    query: str,
    age: Optional[int] = None,
    region: Optional[str] = None,
    is_student: Optional[bool] = None,
    category: Optional[str] = None,
    topics: Optional[List[str]] = None,
    user: User,
    session: Session,
) -> Dict[str, Any]:
    """
    MCP에서 호출되는 실제 Tool 함수
    - run_chat_agent → search_support Tool → 여기로 들어옴
    """

    # 1) 나이 없으면 유저 프로필에서 계산 (YYYYMMDD 또는 YYYY-MM-DD)
    if age is None and getattr(user, "birth", None):
        age = calculate_age_from_birth(user.birth)

    # 2) is_student가 문자열("True"/"False") 로 들어오는 경우 정리
    if isinstance(is_student, str):
        if is_student.lower() == "true":
            is_student = True
        elif is_student.lower() == "false":
            is_student = False
        else:
            is_student = None

    # 3) 실제 검색 로직 호출
    result = search_support_policies_ranked(
        session=session,
        query=query,
        category=category,
        age=age,
        region=region,
        is_student=is_student,
        topics=topics,
    )

    return result

