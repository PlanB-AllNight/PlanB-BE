from typing import Callable, Dict, Any, List, get_origin, get_args, Optional
import inspect

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
        func = self.tools[tool_name]
        return await func(**kwargs)


mcp_registry = ToolRegistry()