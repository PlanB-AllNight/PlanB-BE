from fastapi import APIRouter, Depends
from typing import List
from sqlmodel import Session, select
from backend.database import get_session
from backend.models.support import SupportPolicy, SupportPolicyRead, SupportCategory

router = APIRouter()

@router.get("/policies", response_model=List[SupportPolicyRead])
def get_support_policies(
    category: SupportCategory,  # 카테고리 필터 (예: "장학금/지원금")
    session: Session = Depends(get_session)
):
    """
    특정 카테고리의 모든 정책 목록을 조회합니다.
    - 반환값에 제목, 요약뿐만 아니라 '상세 내용(content, detail)'까지 모두 포함되어 있습니다.
    """
    statement = select(SupportPolicy).where(SupportPolicy.category == category)
    policies = session.exec(statement).all()
    
    return policies