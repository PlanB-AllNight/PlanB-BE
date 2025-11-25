from typing import Optional, Dict, Any
from sqlmodel import Field, SQLModel, Column, JSON
from datetime import datetime, date
from enum import Enum

class PlanType(str, Enum):
    MAINTAIN = "Maintain"
    FRUGAL = "Frugal"
    SUPPORT = "Support"
    INVESTMENT = "Investment"

class ChallengeStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Challenge(SQLModel, table=True):
    __tablename__ = "challenge"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    spending_analysis_id: Optional[int] = Field(default=None, foreign_key="spending_analysis.id")
    
    event_name: str                    # "교환학생", "자취 시작" 등
    current_amount: int                # 현재 보유 금액
    target_amount: int                 # 목표 금액
    shortfall_amount: int              # 부족 금액
    period_months: int                 # 목표 기간
    
    plan_type: PlanType                # 전략 유형
    plan_title: str                    # 전략 제목
    description: str                   # 전략 메시지
    
    monthly_required: int              # 월 저축액
    monthly_shortfall: int             # 월 추가 필요액
    final_estimated_asset: int         # 최종 예상 자산
    expected_period: int               # 예상 달성 기간
    
    # AI 로직용 정보
    plan_detail: Dict[str, Any] = Field(sa_column=Column(JSON))
    # 예: {"target_category": "카페", "reduce_percent": 10, "scholarship_id": 3}
    
    status: ChallengeStatus = Field(default=ChallengeStatus.IN_PROGRESS)
    start_date: date
    end_date: date
    
    created_at: datetime = Field(default_factory=datetime.now)