from typing import Optional, Dict, Any
from pydantic import BaseModel

from typing import Optional, Dict, Any
from pydantic import BaseModel


class MCPRequest(BaseModel):
    # 사용자의 요청 (버튼일 경우 프론트가 "소비 분석해줘"라고 텍스트로 만들어 보냄)
    query: str   
    # 도구 실행에 필요한 구체적 데이터 (선택 사항)
    payload: Dict[str, Any] = {}


class MCPResponse(BaseModel):
    type: str        # "analysis_result", "budget_result", "redirect", "policy_list", "message" 등
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    agent_met: Optional[Dict[str, Any]] = None