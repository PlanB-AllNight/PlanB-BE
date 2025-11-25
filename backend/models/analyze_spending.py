from typing import List, Optional, Dict, Any
from sqlmodel import Field, SQLModel, Relationship
from pydantic import BaseModel
from datetime import datetime, date
from sqlalchemy import Column, JSON

# SpendingAnalysis 테이블
class SpendingAnalysis(SQLModel, table=True):
    __tablename__ = "spending_analysis"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", nullable=False) # (로그인 구현 전까지 1로 고정)
    
    month: str
    analysis_date: date
    
    total_income: int
    total_spent: int
    total_saved: int
    save_potential: int

    daily_average: int
    projected_total: int

    top_category: str
    overspent_category: str

    insight_summary: str
    
    insights: List[Dict[str, Any]] = Field(sa_column=Column(JSON))
    suggestions: List[Dict[str, Any]] = Field(sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=datetime.now)

    category_stats: List["SpendingCategoryStats"] = Relationship(back_populates="analysis")

class SpendingCategoryStats(SQLModel, table=True):
    __tablename__ = "spending_category_stats"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    analysis_id: Optional[int] = Field(default=None, foreign_key="spending_analysis.id")
    
    category_name: str
    amount: int
    count: int
    percent: float

    analysis: Optional[SpendingAnalysis] = Relationship(back_populates="category_stats")


# (DTO) - 프론트엔드용
class CategoryStat(BaseModel):
    category: str
    amount: int
    percent: float

class AnalyzeResponse(BaseModel):
    month: str
    analysis_date: str
    
    total_income: int
    total_spent: int
    total_saved: int
    save_potential: int
    daily_average: int
    projected_total: int
    
    top_category: str
    overspent_category: str
    
    insight_summary: str
    insights: List[Dict[str, Any]]
    suggestions: List[Dict[str, Any]]
    
    chart_data: List[Dict[str, Any]]
    meta: Dict[str, Any]