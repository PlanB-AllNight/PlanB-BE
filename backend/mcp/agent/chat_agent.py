import os
import json
from sqlmodel import Session
from openai import AsyncOpenAI

from backend.models.user import User
from backend.mcp.models import MCPRequest, MCPResponse
from backend.mcp.registry.mcp_registry_chat import mcp_registry_chat

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def run_chat_agent(
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

    [사용 가능 Tool]
    - redirect
    - search_support
    (이 두 개 외의 Tool은 chat_agent에서 절대 호출 금지)

    [사용자 정보]
    - User ID: {user.id}

    [Payload 정보]
    아래 값들은 이미 사용자가 제공한 값입니다. 다시 물어보지 말고 그대로 사용하세요.
    payload = {payload_info}

    [redirect 규칙]
    - 사용자가 기능 페이지 이동을 요청하면 redirect를 호출합니다.
    - redirect(target=...)는 다음 세 가지 중 하나여야 합니다:
        • "analysis"  (소비 분석 화면)
        • "budget"    (예산 추천 화면)
        • "simulate"  (목표 계산 / 챌린지 화면)
    - redirect 대상 문장 예시:
        "소비 분석 해줘", "이번 달 분석 보고 싶어", "분석 페이지로 가줘"
        "예산 추천해줘", "예산 페이지 가자"
        "시뮬레이션 하고 싶어", "목표 계산", "시뮬레이터 가줘"
        "챌린지 만들고 싶어", "챌린지 페이지"
    - 메시지 길게 쓰지 말고 즉시 redirect Tool을 호출하세요.

    [search_support 규칙]
    아래 유형의 문장을 사용자가 말하면 search_support Tool을 호출해야 함.
    - [지원정책/혜택 탐색]
        - "지원금 뭐 있어?"
        - "지원 정책 알려줘"
        - "나 받을 수 있는 지원 있어?"
        - "정부 지원 뭐 있어?"
        - "청년 지원 정책 뭐 있어?"
    - [등록금/장학금 관련]
        - "장학금 뭐 있어?"
        - "등록금 부족한데?"
        - "대학생인데 받을 수 있는 장학금?"
    - [주거/월세 관련]
        - "월세 지원", "보증금 지원", "주거 지원"
    - [취업/취준 관련]
        - "취준생인데 지원 있어?"
        - "취업 지원 정책"
    - [창업/자산 형성]
        - "창업 지원"
        - "사업자 지원"
        - "청년도약계좌 뭐 있어?"
    - [생활비·부족·추가 수입 관련]
        - "생활비 부족해"
        - "알바 외에 돈 더 벌고 싶어"
        - "돈 모자라서 지원 없나?"
        - "추가 소득 필요해"
        - "학생인데 돈 벌기 힘들어"
    - search_support arguments는 다음 5개만 전달합니다:
        {{
            "query": "<사용자 입력 전체 문장>",
            "age": null,
            "region": null,
            "is_student": null,
            "category": null
        }}
    - [Argument 생성 규칙]
        자연어에서 아래 요소가 “명확히 언급되었을 때만” 입력합니다.
        1) 나이(age)
        - “20살”, “20대”, “39세 이하” 등 없으면 null
        2) 학생 여부(is_student)
            True:
                "대학생", "재학생", "학생증", "장학금", "학기", "등록금"
            False:
                "취준생", "직장인", "창업자", "사업자"
            없으면 null
        3) 지역(region)
            자연어에서 특정 지역이 나오면 그대로 사용
            예) "서울", "경기도", "부산"
            없으면 null
        4) category(선택적)
            장학금/등록금 → SCHOLARSHIP
            월세/주거/보증금 → LIVING
            취업/취준 → CAREER
            창업/사업 → ASSET 또는 CAREER
            적금/청년도약계좌 → ASSET
            없으면 null
        5) query
            query는 자연어 전체 문장이 아니라, 정책 검색에 필요한 핵심 키워드만 추출하여 넣으십시오.
            예)  "대학생인데 알바 외 수입원 찾고 싶어"  
                → "대학생 지원"  
                → "대학생 생활비"  
                → "청년 지원금"
            문장 그대로 넣지 마십시오.

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
        tools=mcp_registry_chat.schemas,
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
        result = await mcp_registry_chat.execute(
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