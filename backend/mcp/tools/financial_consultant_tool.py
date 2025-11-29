import json
from typing import Dict, Any, List
from sqlmodel import Session, select, col
from backend.mcp.registry import mcp_registry
from backend.models.user import User
from backend.models.analyze_spending import SpendingAnalysis
from backend.models.challenge import Challenge, ChallengeStatus
from backend.models.support import SupportPolicy, SupportCategory
from backend.ai.client import generate_json
from backend.ai.prompts.consultant_prompt import format_financial_consult_prompt


FINANCIAL_KNOWLEDGE_BASE = {
    "savings": """
    [저축 및 시드머니 모으기 전략]
    - 통장 쪼개기: 급여/용돈(수입), 생활비(지출), 비상금(예비), 저축(투자) 4개 통장으로 분리하여 돈의 흐름을 통제하는 것이 기본입니다.
    - 풍차 돌리기: 매월 1년 만기 적금에 가입하여 1년 뒤부터 매달 만기가 돌아오게 하는 방식으로, 성취감을 느끼기에 최적입니다.
    - 파킹통장(CMA): 하루만 넣어도 이자가 붙는 통장으로, 비상금을 넣어두기에 좋습니다. (토스, 카카오뱅크 세이프박스 등)
    - 6개월 법칙: 투자를 시작하기 전, 최소한 월 생활비의 6배에 해당하는 금액을 비상금으로 먼저 모아야 안전합니다.
    """,
    "investment_entry": """
    [주식 및 투자 입문 가이드]
    - ETF(상장지수펀드): 개별 기업 분석이 어렵다면 시장 전체(S&P500, 나스닥100 등)에 투자하는 ETF가 가장 안전하고 확실한 방법입니다.
    - 소수점 투자: 스타벅스 커피 1잔 값(5천원)으로 비싼 미국 우량주(애플, 테슬라 등)를 0.1주씩 모을 수 있습니다. (토스증권, 미니스탁 활용)
    - 적립식 매수: 주가 등락에 일희일비하지 말고, 매월 날짜를 정해 기계적으로 매수하는 것이 승률이 가장 높습니다.
    - ISA 계좌: '만능 통장'이라 불리며, 주식/펀드 매매 차익에 대해 비과세 혜택(200만원~400만원)이 있어 사회초년생 필수 계좌입니다.
    """,
    "study": """
    [금융 공부 추천 자료]
    - 입문 필독서: '돈의 속성(김승호)', '부자 아빠 가난한 아빠(로버트 기요사키)', '주식투자 무작정 따라하기(윤재수)'
    - 추천 유튜브: '슈카월드'(재미있는 경제 이슈), '신사임당'(재테크 마인드), '삼프로TV'(시장 시황), '전인구경제연구소'
    - 필수 기초 개념: 복리 효과(72의 법칙), 인플레이션, 금리와 주가의 관계, PER/PBR/ROE 용어 이해.
    """,
    "housing": """
    [주거 독립 및 청약]
    - 청년 주택드림 청약통장: 만 19~34세 필수 가입. 이자율 최대 4.5%에 나중에 주택 구입 시 저리 대출 연계까지 가능합니다.
    - 중기청 대출: 중소기업 취업 청년이라면 연 1.2% 금리로 최대 1억원 전세 보증금 대출이 가능합니다. (가장 혜택이 큼)
    - 버팀목 전세자금대출: 무주택 청년 대상 저금리 전세 대출입니다.
    - 월세 세액공제: 연봉 7천만원 이하 무주택 세대주는 연말정산 시 낸 월세의 15~17%를 환급받을 수 있습니다. (전입신고 필수)
    """
}

def get_relevant_policies(session: Session, topic: str) -> str:
    """
    주제와 연관된 정책을 DB에서 조회. (범용성: 없으면 빈 문자열 반환)
    """
    category_map = {
        "savings": [SupportCategory.ASSET],
        "investment_entry": [SupportCategory.ASSET],
        "study": [SupportCategory.CAREER, SupportCategory.SCHOLARSHIP],
        "housing": [SupportCategory.LIVING],
        "general": [] 
    }
    
    target_categories = category_map.get(topic, [])
    if not target_categories:
        return ""

    # 관련 정책 3개만 조회
    query = select(SupportPolicy).where(col(SupportPolicy.category).in_(target_categories))
    policies = session.exec(query.limit(3)).all()
    
    if not policies:
        return "" # 관련 정책 없으면 빈 문자열 (범용 상담으로 전환)
        
    policy_text = "[추천 가능한 관련 지원 정책]\n"
    for p in policies:
        policy_text += f"- {p.title}: {p.subtitle}\n"
        
    return policy_text

def get_user_financial_context(user: User, session: Session) -> Dict[str, Any]:
    """사용자의 최신 재무 데이터와 챌린지 상태 조회"""
    context = {"has_data": False}
    
    #  최신 소비 분석
    analysis = session.exec(
        select(SpendingAnalysis)
        .where(SpendingAnalysis.user_id == user.id)
        .order_by(SpendingAnalysis.created_at.desc())
    ).first()
    
    if analysis:
        context.update({
            "has_data": True,
            "month": analysis.month,
            "income": analysis.total_income,
            "spent": analysis.total_spent,
            "save_potential": analysis.save_potential,
            "overspent": analysis.overspent_category
        })
        
    #  진행 중인 챌린지
    challenge = session.exec(
        select(Challenge)
        .where(Challenge.user_id == user.id)
        .where(Challenge.status == ChallengeStatus.IN_PROGRESS)
    ).first()
    
    if challenge:
        context.update({
            "challenge_name": challenge.challenge_name,
            "target_amount": challenge.target_amount
        })
        
    return context

@mcp_registry.register(
    name="consult_financial_advisor",
    description="금융 관련 고민(저축, 투자, 주식 공부, 목돈 마련 등)에 대해 사용자의 재무 상황을 고려하여 전문적인 조언을 제공합니다. 질문(query)과 주제(topic)를 입력받습니다."
)
async def consult_financial_advisor(
    user: User,
    session: Session,
    query: str,
    topic: str = "general" # savings, investment_entry, study, housing, general
) -> Dict[str, Any]:
    """
    [MCP Tool] AI 금융 상담사
    """
    #  사용자 문맥 데이터 조회
    user_context = get_user_financial_context(user, session)

    #  관련 정책 (우리 DB)
    relevant_policies = get_relevant_policies(session, topic)
    
    #  지식 베이스 매핑 (Topic 기반)
    # topic이 명확하지 않으면 전체 지식을 요약해서 주거나, query 키워드로 찾음
    knowledge = FINANCIAL_KNOWLEDGE_BASE.get(topic, "")
    if not knowledge or topic == "general":
        if "주식" in query or "투자" in query:
            knowledge += FINANCIAL_KNOWLEDGE_BASE["investment_entry"]
        elif "저축" in query or "모으" in query or "적금" in query or "돈" in query:
            knowledge += FINANCIAL_KNOWLEDGE_BASE["savings"]
        elif "공부" in query or "책" in query:
            knowledge += FINANCIAL_KNOWLEDGE_BASE["study"]
        elif "집" in query or "청약" in query or "월세" in query:
            knowledge += FINANCIAL_KNOWLEDGE_BASE["housing"]
        else: knowledge = "일반적인 금융 상식에 기반하여 답변하세요."
            
    full_knowledge = f"""
    {knowledge}

    {relevant_policies}
    (위 정책 목록이 있다면, 조언 과정에서 구체적인 해결책으로 언급해주세요. 없다면 일반적인 조언을 해주세요.)
    """

    prompt = format_financial_consult_prompt(
        user_name=user.name,
        query=query,
        topic=topic,
        user_context=user_context,
        knowledge_base=full_knowledge
    )
    
    system_msg = "당신은 최고의 대학생 금융 멘토입니다. JSON으로만 응답하세요."
    try:
        response = generate_json(system_msg, prompt, temperature=0.7)
        content = json.loads(response.choices[0].message.content)
        
        return {
            "status": "success",
            "topic": topic,
            "consultation": content
        }
        
    except Exception as e:
        print(f"AI 상담 생성 실패: {e}")
        return {
            "status": "error",
            "message": "죄송합니다. 현재 금융 상담 AI가 잠시 생각에 잠겨있네요. 잠시 후 다시 시도해주세요."
        }