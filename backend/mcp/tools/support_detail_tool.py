from sqlmodel import Session, select
from backend.models.support import SupportPolicy
from backend.mcp.registry.mcp_registry_chat import mcp_registry_chat

@mcp_registry_chat.register(
    name="support_detail",
    description="사용자가 특정 지원 정책의 이름(예: '국가장학금')을 말했을 때, 해당 정책의 상세 정보를 조회합니다."
)
async def get_support_detail_by_name(support_detail: str, session: Session, **kwargs) -> dict:
    """
    정책 이름으로 상세 정보 조회
    """
    # 1. 정확한 이름 검색
    statement = select(SupportPolicy).where(SupportPolicy.title == support_detail)
    policy = session.exec(statement).first()
    
    # 2. 정확한 매칭이 없으면 포함 검색 (유연성)
    if not policy:
        statement = select(SupportPolicy).where(SupportPolicy.title.contains(support_detail))
        policy = session.exec(statement).first()
    
    if not policy:
        return {
            "found": False,
            "message": f"'{support_detail}'에 대한 정보를 찾을 수 없어요. 정확한 명칭을 다시 말씀해 주시겠어요?"
        }

    # 3. 상세 정보 반환 (모달에 띄울 내용 포함)
    return {
        "found": True,
        "policy": {
            "id": policy.id,
            "title": policy.title,
            "subtitle": policy.subtitle,
            "category": policy.category.value,
            "institution": policy.institution,
            "apply_period": policy.apply_period,
            "target": policy.target,
            "pay_method": policy.pay_method,
            "content": policy.content,  # 상세 본문
            "application_url": policy.application_url
        }
    }