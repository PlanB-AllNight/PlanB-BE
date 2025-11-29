import os
import json
from sqlmodel import Session
from openai import AsyncOpenAI

from backend.models.user import User
from backend.mcp.models import MCPRequest, MCPResponse
from backend.mcp.registry.mcp_registry_finance import mcp_registry_finance

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def run_financial_agent(
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
    payload_info = json.dumps(req.payload, ensure_ascii=False)
    user_text = req.query

    print(f"[MCP AGENT] Query='{user_text}'")

    # ------------------------------
    # 2) MCP 스타일 시스템 프롬프트
    # ------------------------------
    system_prompt = f"""
    당신은 'PlanB AI Agent'이며, MCP Server 규칙을 따릅니다.

    [사용자 정보]
    - User ID: {user.id}

    [Payload 정보]
    아래 값들은 이미 사용자가 제공한 값입니다. 다시 물어보지 말고 그대로 사용하세요.
    payload = {payload_info}

    ## [답변 규칙]
    - 사용자는 명령을 직접 실행하려고 함
    - 절대 긴 설명 금지
    - 즉시 적절한 MCP Tool을 호출해야 함
    - 호출할 수 있는 MCP Tool은 다음과 같음(중요):
        recommend_budget, simulate_event, analyze_spending, create_challenge
        이 외의 Tool은 호출하지 않아야 합니다.

    [소비 분석(analyze_spending)]
    - 사용자가 월을 입력하지 않아도 됩니다.
    - month가 없으면 Tool(analyze_spending)이 자동으로 최신 데이터를 선택합니다.
    - 절대 "몇 월을 분석할까요?"라고 물어보지 마세요.
    - 요청이 '분석'과 관련 있으면 바로 analyze_spending Tool을 실행하세요.
    
    [예산 추천(recommend_budget)]
    - plan_type이 없으면 절대 사용자에게 물어보지 마세요.
    - 무조건 기본값 '50/30/20'을 사용하세요.
    - 질문을 유도하지 말고 즉시 도구를 실행하세요.

    [simulate_event 규칙]
    1. 사용자가 "시뮬레이션", "챌린지", "목표", "얼마 모아야 해", 
        "얼마 필요해", "축의금", "결혼", "출산", "유학" 등
        재무 목표 관련 표현을 쓰면 simulate_event Tool을 사용해야 합니다.
    2. request.payload 안에 다음 값이 있다면 즉시 Tool을 실행합니다:
        - event_name
        - target_amount
        - period
        - current_asset
        - monthly_save_potential
    3. payload가 존재하고 값이 모두 들어있다면 절대 질문하지 말고 simulate_event Tool을 호출하세요.
    4. source === "button" 또는 context.screen === "simulate"일 경우 무조건 simulate_event Tool을 호출해야 합니다.
    5. 값이 일부만 비어있을 때만 사용자에게 질문합니다.

    [create_challenge 규칙]
    아래 조건이 충족되면 create_challenge Tool을 자동으로 실행해야 합니다.
    1. payload에 아래 값들이 모두 존재하거나  
        Tool 선택 직후 AI가 tool_call로 파라미터를 모두 제공할 수 있을 때:
            - event_name
            - target_amount
            - period_months
            - current_amount
            - challenge_name
            - plan_type
            - plan_title
            - description
            - monthly_required
            - monthly_shortfall
            - final_estimated_asset
            - expected_period
            - plan_detail
    2. 질문 금지:
        - payload에 값이 있는데도 다시 묻지 말 것.
        - "정말 챌린지를 생성할까요?" 같은 유도 질문 절대 금지.
    3. simulate_event 이후 사용자가 “이걸로 챌린지 만들래”,  
        “챌린지 생성”, “이 플랜으로 진행” 등 말하면 create_challenge Tool 호출

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
        tools=mcp_registry_finance.schemas,
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
        result = await mcp_registry_finance.execute(
            tool_name=tool_name,
            user=user,
            session=session,
            **final_args
        )

        return {
            "type": "tool_result",
            "tool": tool_name,
            "data": result,
            "action": "Executed MCP Tool"
        }

    # ------------------------------
    # 5) Tool 사용 없이 메시지만 반환
    # ------------------------------
    return {
        "type": "message",
        "message": msg.content,
        "action": "Chat response"
    }