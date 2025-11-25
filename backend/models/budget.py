from sqlmodel import Field, SQLModel
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum

class PlanType(str, Enum):
    fifty = "50/30/20"
    sixty = "60/20/20"
    forty = "40/30/30"

class BudgetAnalysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    spending_analysis_id: int = Field(foreign_key="spendinganalysis.id")

    plan_type: PlanType
    essential_budget: int
    optional_budget: int
    saving_budget: int

    category_proposals: str  # JSON 형식 그대로 저장
    ai_proposal: str  # JSON 형식 그대로 저장

    created_at: datetime = Field(default_factory=datetime.now)

# === 요청 & 응답 DTO === #
# 카테고리별 예산 상세
class CategoryBudget(BaseModel):
    category: str
    current: int
    budget: int
    status: str  # 과소비/적정/여유

# 요약 정보 (상단 카드)
class BudgetSummaryItem(BaseModel):
    amount: int
    percent: int

class BudgetSummary(BaseModel):
    needs: BudgetSummaryItem
    wants: BudgetSummaryItem
    savings: BudgetSummaryItem

# 최종 응답 DTO (프론트엔드용)
class BudgetResponse(BaseModel):
    total_income: int
    selected_plan: str  # "50/30/20"
    budget_summary: BudgetSummary
    category_proposals: Dict[str, List[CategoryBudget]]  # {"needs": [...], "wants": [...], "savings": [...]}
    ai_proposal: List[str]

# 요청 DTO
class BudgetRequest(BaseModel):
    selected_plan: str = "40/30/30" # enum 형식으로 받음 (default: 40/30/30 룰)