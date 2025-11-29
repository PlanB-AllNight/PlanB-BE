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
    payload_info = json.dumps(req.payload, ensure_ascii=False)
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

    [Payload 정보]
    아래 값들은 이미 사용자가 제공한 값입니다. 다시 물어보지 말고 그대로 사용하세요.
    payload = {payload_info}

    ## [Source 규칙]
    1) source='button'
        - 사용자는 명령을 직접 실행하려고 함
        - 절대 긴 설명 금지
        - 즉시 적절한 MCP Tool을 호출해야 함

    2) source='chat'
        - 사용자가 아래와 같은 요청을 하면, 절대 직접 MCP Tool(analyze_spending, recommend_budget, simulate_event, create_challenge)을 호출하지 마세요.
            예: "소비 분석해줘", "이번 달 분석", "예산 추천해줘", "예산 알려줘", "시뮬레이션 하고 싶어", "목표 계산할래",
                "챌린지 만들고 싶어", "챌린지 생성"
        - 이런 자연어 요청은 반드시 redirect Tool을 호출해 사용자를 해당 화면으로 이동시키는 방식으로 처리합니다.
        - 사용자는 금융 상담을 원함
        - 필요 시 MCP Tool을 호출해 실데이터 기반 조언
        - "이동"/"분석해줘"/"예산 추천해줘" 등 자연어는 tool로 변환

    [중요 규칙 - 소비 분석(analyze_spending)]
    - 사용자가 월을 입력하지 않아도 됩니다.
    - month가 없으면 Tool(analyze_spending)이 자동으로 최신 데이터를 선택합니다.
    - 절대 "몇 월을 분석할까요?"라고 물어보지 마세요.
    - 요청이 '분석'과 관련 있으면 바로 analyze_spending Tool을 실행하세요.
    
    [중요 규칙 - 예산 추천(recommend_budget)]
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
        “챌린지 생성”, “이 플랜으로 진행” 등 말하면 create_challenge Tool 호출.

    [금융 상담 및 교육 (consult_financial_advisor)]
    1. 사용자가 다음과 같은 "고민 상담"이나 "방법론", "교육"을 원할 때 이 Tool을 사용하세요.
       - "돈 어떻게 모아야 해?", "현실적인 저축 방법 알려줘"
       - "주식 처음인데 어떻게 해?", "주식 공부 책 추천해줘"
       - "시드머니 모으는 법", "통장 쪼개기가 뭐야?"
       - "집 사려면 어떻게 해야 해?", "청약이 뭐야?"
    - ★매우 중요★: "CMA가 뭐야?", "ETF가 뭔데?", "공매도가 뭐야?" 같이 **단순한 금융 용어 정의나 개념을 묻는 질문에도 반드시 이 Tool을 사용하세요.**
    2. 파라미터 `topic`은 질문 내용에 따라 아래 중 하나를 선택하세요.
       - 저축/목돈/시드머니/통장쪼개기: "savings"
       - 주식/투자시작/소수점 투자/ETF: "investment_entry"
       - 공부/자료/책 추천/유튜브 채널: "study"
       - 주거/청약/전세/월세/독립: "housing"
       - 기타/일반적 재무 고민: "general"
    3. 단순한 '정책 검색'(장학금 찾아줘)은 `get_support_info`를 쓰고, 
       '조언/전략/교육'이 필요하면 `consult_financial_advisor`를 쓰세요.

    [또래 소비 비교 (compare_with_peers)]
       - 사용자가 "나 많이 쓰는 편이야?", "남들은 식비 얼마나 써?", "평균이랑 비교해줘", "내 소비 수준 어때?" 같이 **타인과의 비교**를 원할 때 사용하세요.
       - `category` 파라미터는 질문 내용을 보고 추론하세요 (예: "식비 비교해줘" -> "식사").
       - ★중요★ 사용자가 특정 카테고리를 언급하지 않았다면, **사용자에게 되묻지 말고 무조건 "전체"로 설정하여 즉시 Tool을 실행하세요.**

    [redirect 규칙]
    - 사용자가 "예산 추천 페이지로 가줘", "시뮬레이션 하러 갈래" 등 페이지 이동을 요청하면 redirect Tool을 호출하십시오.
    - redirect Tool의 파라미터 target은 다음 중 하나여야 합니다:
        ["analysis", "budget", "simulate"]
    - redirect Tool의 target 매핑은 다음과 같습니다.
        - 소비 분석 관련 -> target="analysis"
        - 예산 추천 관련 -> target="budget"
        - 시뮬레이션 관련 -> target="simulate"
        - 챌린지 생성은 시뮬레이션 화면으로 이동 -> target="simulate"
    - 프론트에서 이동하기 때문에 메시지를 길게 쓰지 마세요.

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