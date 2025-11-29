from typing import Callable, Dict, Any, List, get_origin, get_args, Optional
import inspect

from backend.mcp.templates.build_message import build_support_message

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []

    # --------------------------------------------------------
    # Python 타입 힌트 → JSON Schema 타입
    # --------------------------------------------------------
    def _python_type_to_schema(self, annotation):
        origin = get_origin(annotation)
        args = get_args(annotation)

        # Optional[X] → ["type_of_X", "null"]
        if origin is Optional:
            inner = self._python_type_to_schema(args[0])
            t = inner["type"]
            if isinstance(t, list):
                return {"type": t + ["null"]}
            return {"type": [t, "null"]}

        # 기본 타입 매핑
        if annotation is str:
            return {"type": "string"}
        if annotation is int:
            return {"type": "integer"}
        if annotation is bool:
            return {"type": "boolean"}

        # List[X]
        if origin in (list, List):
            item_schema = self._python_type_to_schema(args[0])
            return {
                "type": "array",
                "items": item_schema
            }

        # fallback
        return {"type": "string"}

    # --------------------------------------------------------
    # MCP Tool 등록 데코레이터
    # --------------------------------------------------------
    def register(self, name: str, description: str):
        def decorator(func: Callable):
            self.tools[name] = func

            sig = inspect.signature(func)
            props = {}
            required = []

            for pname, p in sig.parameters.items():
                # 내부 DI 요소는 제외
                if pname in ("user", "session", "kwargs", "args"):
                    continue

                # 타입 힌트 기반 JSON schema 생성
                annotation = p.annotation
                props[pname] = self._python_type_to_schema(annotation)
                required.append(pname)

            schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    }
                }
            }

            self.schemas.append(schema)
            print(f"✅ MCP Tool registered: {name}")
            return func

        return decorator

    # --------------------------------------------------------
    # Tool 실행
    # --------------------------------------------------------
    async def execute(self, tool_name: str, **kwargs):
        if tool_name not in self.tools:
            raise ValueError(f"Unknown MCP Tool: {tool_name}")
        
        tool_func = self.tools[tool_name]
        result = await tool_func(**kwargs)

        # 자연어 후처리: 검색 결과는 사람이 읽기 좋게 변환
        if tool_name == "search_support":
            real_data = result.get("data", [])
            msg = build_support_message(
                query=kwargs.get("query", ""),
                results=real_data
            )
            
            # [수정] 문자열(msg)을 바로 리턴하지 말고, 딕셔너리로 포장해야 함!
            return {
                "type": "chat_response",  # 프론트엔드가 알 수 있는 타입
                "message": msg,           # 텍스트는 여기에 담기
                "data": real_data,           # 원본 데이터도 같이 주면 좋음
                "success": True
            }
        
        if tool_name == "support_detail":
            if result["found"]:
                policy = result["policy"]
                
                # [핵심] 챗봇의 말풍선 멘트
                ai_message = f"""
🎓 <b>{policy['title']}</b>에 대해 알려드릴게요!<br/>

{policy['subtitle']}<br/><br/>

✅ <b>누가 받을 수 있나요?</b><br/>
{policy['target']}<br/><br/>

📅 <b>신청은 언제인가요?</b><br/>
{policy['apply_period']}<br/><br/>

💰 <b>어떻게 지급되나요?</b><br/>
{policy['pay_method']}<br/><br/>

📝 <b>상세 내용</b><br/>
{policy['content']}<br/><br/>

👉 <a href="{policy['application_url']}" target="_blank">공식 사이트에서 더 보기</a>
"""

                
                return {
                    "type": "chat_response",
                    "message": ai_message,
                    "data": {
                        "type": "markdown",
                        "policy": policy
                    },
                    "success": True
                }
            else:
                # 못 찾았을 때
                return {
                    "type": "chat_response",
                    "message": result["message"],
                    "data": None,
                    "success": False
                }

        return result
    

mcp_registry_chat = ToolRegistry()