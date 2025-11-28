from typing import Optional, Dict, Any, List
from sqlmodel import Field, SQLModel, Column, JSON
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, field_validator

class PlanType(str, Enum):
    MAINTAIN = "MAINTAIN"
    FRUGAL = "FRUGAL"
    SUPPORT = "SUPPORT"
    INVESTMENT = "INVESTMENT"


class ChallengeStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"  # 진행 중
    COMPLETED = "COMPLETED"      # 완료
    FAILED = "FAILED"            # 실패/포기


class Challenge(SQLModel, table=True):
    __tablename__ = "challenge"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    spending_analysis_id: Optional[int] = Field(
        default=None, 
        foreign_key="spending_analysis.id",
        description="연결된 소비분석 ID (챌린지 생성 시점의 최신 분석)"
    )
    
    # 목표 정보
    event_name: str = Field(description="이벤트 이름 (교환학생, 노트북 구매 등)")
    current_amount: int = Field(description="챌린지 시작 시점의 보유 금액")
    target_amount: int = Field(description="목표 금액")
    shortfall_amount: int = Field(description="부족 금액 (target - current)")
    period_months: int = Field(description="목표 기간(개월) - 사용자가 설정한 기간")
    
    # 플랜 정보
    plan_type: PlanType = Field(description="선택한 플랜 유형")
    plan_title: str = Field(description="플랜 제목 (현상 유지, 초절약 플랜 등)")
    description: str = Field(description="플랜 설명 (전략 메시지)")
    
    # 재무 정보
    monthly_required: int = Field(description="필요한 월 저축액")
    monthly_shortfall: int = Field(description="추가로 필요한 월 저축액")
    final_estimated_asset: int = Field(description="최종 예상 자산")
    expected_period: int = Field(description="플랜 기준 예상 달성 기간(개월)")
    
    # AI 로직용 메타 정보 (JSON)
    plan_detail: Dict[str, Any] = Field(
        sa_column=Column(JSON),
        description="AI가 다음 소비분석 시 참고할 정보",
        default_factory=dict
    )
    # 예시: {
    #   "target_categories": ["카페/디저트", "쇼핑/꾸미기"],
    #   "reduce_percent": 15,
    #   "scholarship_id": 2,
    #   "sto_product_id": "STO_001",
    #   "efficiency": 5.2
    # }
    
    # 상태 및 날짜
    status: ChallengeStatus = Field(default=ChallengeStatus.IN_PROGRESS)
    start_date: date = Field(description="챌린지 시작일")
    end_date: date = Field(description="목표 종료일 (목표 기간 기준)")
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default=None)



class ChallengeInitResponse(BaseModel):
    current_asset: int
    monthly_save_potential: int
    has_analysis: bool
    last_analysis_date: Optional[str] = None
    latest_mydata_date: Optional[str] = None
    analysis_outdated: bool = False


class SimulateRequest(BaseModel):
    event_name: str
    target_amount: int
    period: int  # 목표 기간(개월)
    current_asset: Optional[int] = None
    monthly_save_potential: Optional[int] = None
    
    @field_validator('target_amount')
    @classmethod
    def validate_target_amount(cls, v):
        if v <= 0:
            raise ValueError("목표 금액은 0보다 커야 합니다.")
        return v
    
    @field_validator('period')
    @classmethod
    def validate_period(cls, v):
        if v <= 0:
            raise ValueError("목표 기간은 0보다 커야 합니다.")
        if v > 600:  # 50년
            raise ValueError("목표 기간은 최대 600개월(50년)입니다.")
        return v


class SimulateResponse(BaseModel):
    event_name: str
    target_amount: int
    current_amount: int
    shortfall_amount: int
    period_months: int
    monthly_save_potential: int
    
    situation_analysis: Dict[str, Any]
    plans: List[Dict[str, Any]]
    
    ai_summary: str
    recommendation: str
    
    simulation_date: str
    meta: Dict[str, Any]


class CreateChallengeRequest(BaseModel):
    # 목표 정보
    event_name: str
    target_amount: int
    period_months: int
    current_amount: int
    
    # 선택한 플랜 정보
    plan_type: PlanType
    plan_title: str
    description: str
    monthly_required: int
    monthly_shortfall: int
    final_estimated_asset: int
    expected_period: int
    
    # 메타 정보
    plan_detail: Dict[str, Any] = {}
    
    @field_validator('target_amount', 'current_amount')
    @classmethod
    def validate_amounts(cls, v):
        if v < 0:
            raise ValueError("금액은 0 이상이어야 합니다.")
        return v


class ChallengeResponse(BaseModel):
    id: int
    event_name: str
    plan_title: str
    status: str
    start_date: date
    end_date: date
    message: str
    is_new: bool = True


class ChallengeListItem(BaseModel):
    id: int
    event_name: str
    plan_title: str
    target_amount: int
    current_amount: int
    period_months: int
    monthly_required: int
    status: ChallengeStatus
    start_date: date
    end_date: date
    progress_percent: Optional[int] = None
    
    class Config:
        from_attributes = True


class ChallengeDetailResponse(BaseModel):
    id: int
    event_name: str
    
    current_amount: int
    target_amount: int
    shortfall_amount: int
    period_months: int
    
    plan_type: PlanType
    plan_title: str
    description: str
    
    monthly_required: int
    monthly_shortfall: int
    final_estimated_asset: int
    expected_period: int
    
    status: ChallengeStatus
    start_date: date
    end_date: date
    created_at: datetime
    
    plan_detail: Dict[str, Any]
    
    class Config:
        from_attributes = True