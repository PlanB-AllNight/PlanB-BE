from typing import List, Optional
from sqlmodel import Field, SQLModel
from pydantic import BaseModel
from datetime import datetime
import json

# SpendingAnalysis 테이블
class SpendingAnalysis(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", nullable=False) # (로그인 구현 전까지 1로 고정)
    
    month: str = Field(index=True) # 예: "2024-11"
    
    # 핵심 숫자 데이터
    total_income: int
    total_spent: int
    save_potential: int
    top_category: str
    
    # 리스트 데이터 (JSON 문자열로 저장)
    # 예: "['식비가 가장 큼', '카페 빈도 높음']"
    insight_list_json: str = "[]"
    suggestion_list_json: str = "[]"
    summary_suggestion: str # 한 줄 요약
    
    created_at: datetime = Field(default_factory=datetime.now)

    # DB에서 꺼낼 때 JSON 문자열을 리스트로 변환해주는 함수
    def get_insight_list(self) -> List[str]:
        return json.loads(self.insight_list_json)

    def get_suggestion_list(self) -> List[str]:
        return json.loads(self.suggestion_list_json)


# (DTO) - 프론트엔드용
class CategoryStat(BaseModel):
    category: str
    amount: int
    percent: float

class AnalyzeResponse(BaseModel):
    month: str
    total_income: int
    total_spent: int
    save_potential: int
    categories: List[CategoryStat]

    most_spent_category: str
    overspent_category: str
    overspent_desc: str
    summary_suggestion: str
    
    insight_list: List[str]
    suggestion_list: List[str]