import os
import json
from sqlmodel import Session
from openai import AsyncOpenAI

from backend.models.user import User
from backend.mcp.models import MCPRequest, MCPResponse
from backend.mcp.registry import mcp_registry

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def run_mcp_agent(
    req: MCPRequest,
    user: User,
    session: Session
) -> dict:
    """
    완전한 Pure MCP Server 스타일의 Agent Router
    LLM이 tool 선택 → registry tool 실행 → 결과 통일된 JSON 반환
    """
    
    # ------------------------------
    # 1) Context 가져오기
    # ------------------------------
    source = req.context.get("source", "chat")       # chat or button
    screen = req.context.get("screen", "unknown")
    user_text = req.query

    print(f"[MCP AGENT] Source={source} Screen={screen} Query='{user_text}'")

    # ------------------------------
    # 2) MCP 스타일 시스템 프롬프트
    # ------------------------------
    system_prompt = f"""
    당신은 'PlanB AI Agent'이며, MCP Server 규칙을 따릅니다.

    [사용자 정보]
    - User ID: {user.id}

    [현재 화면]
    - {screen}

    [중요 규칙 - 소비 분석(analyze_spending)]
    - 사용자가 월을 입력하지 않아도 됩니다.
    - month가 없으면 Tool(analyze_spending)이 자동으로 최신 데이터를 선택합니다.
    - 절대 "몇 월을 분석할까요?"라고 물어보지 마세요.
    - 요청이 '분석'과 관련 있으면 바로 analyze_spending Tool을 실행하세요.
    
    [중요 규칙 - 예산 추천(recommend_budget)]
    - plan_type이 없으면 절대 사용자에게 물어보지 마세요.
    - 무조건 기본값 '50/30/20'을 사용하세요.
    - 질문을 유도하지 말고 즉시 도구를 실행하세요.

    [Source 규칙]
    1) source='button'
       - 사용자는 명령을 직접 실행하려고 함
       - 절대 긴 설명 금지
       - 즉시 적절한 MCP Tool을 호출해야 함

    2) source='chat'
       - 사용자는 금융 상담을 원함
       - 필요 시 MCP Tool을 호출해 실데이터 기반 조언
       - "이동"/"분석해줘"/"예산 추천해줘" 등 자연어는 tool로 변환

    [응답 규칙]
    - 반드시 하나의 tool을 선택하거나, 메시지(text)로 답하세요
    - 함수 이름과 파라미터는 제공된 MCP Tool 스키마만 사용하세요
    """

    # ------------------------------
    # 3) GPT에 Tool Schema + 사용자 질문 전달
    # ------------------------------
    completion = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        tools=mcp_registry.schemas,
        tool_choice="auto"
    )
    
    msg = completion.choices[0].message

    # ------------------------------
    # 4) AI가 Tool을 선택했는지 확인
    # ------------------------------
    if msg.tool_calls:
        tool_call = msg.tool_calls[0]
        tool_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        print(f"[MCP AGENT] AI selected tool: {tool_name} args={args}")

        # payload (버튼에서 넘어오는 데이터)와 합치기
        final_args = {**args, **req.payload}

        # registry에서 함수 실행
        result = await mcp_registry.execute(
            tool_name=tool_name,
            user=user,
            session=session,
            **final_args
        )

        return {
            "type": "tool_result",
            "tool": tool_name,
            "data": result,
            "agent_trace": {
                "source": source,
                "screen": screen,
                "action": "Executed MCP Tool"
            }
        }

    # ------------------------------
    # 5) Tool 사용 없이 메시지만 반환
    # ------------------------------
    return {
        "type": "message",
        "message": msg.content,
        "agent_trace": {
            "source": source,
            "screen": screen,
            "action": "Chat response"
        }
    }