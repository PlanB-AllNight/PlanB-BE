from typing import Optional
from pydantic import BaseModel
from sqlmodel import Field, SQLModel
from enum import Enum

# 정책 카테고리 Enum 정의
class SupportCategory(str, Enum):
    SCHOLARSHIP = "장학금/지원금"
    LOAN = "대출 상품"
    LIVING = "생활/복지"
    CAREER = "취업/진로"
    ASSET = "자산 형성"

# 지원 정책 테이블 (Entity)
class SupportPolicy(SQLModel, table=True):
    __tablename__ = "support_info"

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # 카테고리 (Enum 사용)
    category: SupportCategory 
    
    # 기본 정보 (카드 UI용)
    title: str = Field(unique=True, index=True)  # 정책 이름 (검색을 위해 index 설정)
    subtitle: str                   # 한 줄 요약 설명
    
    # 핵심 요약 정보
    institution: str                # 제공 기관
    apply_period: str               # 신청 기간 (예: 4월 중순 ~ 5월)
    target: str                     # 지원 대상 (예: 대학 재학생, 소득 4분위)
    pay_method: str                 # 지급 방식
    
    # 상세 정보 (모달 팝업용)
    content: str                    # 지원 내용 상세 본문
    
    # 링크
    application_url: str            # '공식 사이트' 또는 '신청하기' 링크

    # AI/검색/필터용
    keywords: Optional[str]

# 응답용 DTO
class SupportPolicyRead(BaseModel):
    id: int
    category: SupportCategory
    title: str
    subtitle: str
    institution: str
    apply_period: str
    target: str
    pay_method: str
    content: str
    application_url: str