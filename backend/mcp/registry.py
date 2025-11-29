from typing import Callable, Dict, Any, List
import inspect
import json

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []

    def register(self, name: str, description: str):
        """
        MCP Tool 등록 데코레이터
        """
        def decorator(func: Callable):
            self.tools[name] = func

            # 파라미터 스키마 자동 생성
            sig = inspect.signature(func)
            params = {}
            for pname, p in sig.parameters.items():
                if pname in ("user", "session", "kwargs", "args"):
                    continue  # 내부 DI 제외

                params[pname] = {"type": "string"}  # 기본 string

            schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": params,
                        "required": list(params.keys()),
                    }
                }
            }

            self.schemas.append(schema)
            print(f"✅ MCP Tool registered: {name}")
            return func
        return decorator

    async def execute(self, tool_name: str, **kwargs):
        """
        AI가 Tool Call을 생성했을 때 실제로 Python 함수를 실행
        """
        if tool_name not in self.tools:
            raise ValueError(f"Unknown MCP Tool: {tool_name}")

        func = self.tools[tool_name]

        result = await func(**kwargs)

        # MCP 표준: 항상 dict 반환
        return result


mcp_registry = ToolRegistry()