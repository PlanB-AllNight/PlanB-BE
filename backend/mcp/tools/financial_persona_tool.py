import json
import pandas as pd
import os
from typing import Dict, Any
from sqlmodel import Session
from backend.mcp.registry.mcp_registry_chat import mcp_registry_chat
from backend.models.user import User
from backend.services.spending.analyze_spending import DATA_PATH, CATEGORY_MAP

PERSONAS = {
    "SAVER": {
        "title": "숨만 쉬어도 부자 💰",
        "desc": "놀라운 저축 본능! 통장에 돈이 쌓이는 소리가 들리네요.",
        "tags": ["#저축왕", "#짠테크", "#미래의건물주"]
    },
    "NIGHT_OWL": {
        "title": "달빛 야식 요정 🦉",
        "desc": "밤만 되면 배고픈 당신! 배달 앱 VIP가 될 기세군요.",
        "tags": ["#야식스타그램", "#배달의기수", "#밤샘러"]
    },
    "CAFE_LOVER": {
        "title": "카페인 연금술사 ☕️",
        "desc": "혈관에 커피가 흐르는 당신! 카페 사장님의 최애 고객입니다.",
        "tags": ["#1일3카페", "#카공족", "#디저트배따로"]
    },
    "INSIDER": {
        "title": "이 구역의 핵인싸 🍻",
        "desc": "모임과 술자리는 빠질 수 없죠. 당신의 간은 안녕하신가요?",
        "tags": ["#술스타그램", "#N빵요정", "#분위기메이커"]
    },
    "SHOPPER": {
        "title": "택배 기사님 절친 📦",
        "desc": "스트레스는 쇼핑으로 푼다! 문 앞에 택배가 끊이질 않네요.",
        "tags": ["#지름신", "#탕진잼", "#패션피플"]
    },
    "CVS_VIP": {
        "title": "편의점 미슐랭 🏪",
        "desc": "하루의 시작과 끝을 편의점에서! 신상 젤리는 못 참죠.",
        "tags": ["#2+1사랑", "#편의점털기", "#간식요정"]
    },
    "TAXI_RIDER": {
        "title": "아스팔트의 귀족 🚖",
        "desc": "조금만 늦어도 택시 호출! 대중교통보다 뒷자리가 편한 당신.",
        "tags": ["#택시비폭탄", "#지각면제권", "#편안함추구"]
    },
    "BALANCE": {
        "title": "황금 밸런스 마스터 ⚖️",
        "desc": "어느 한쪽에 치우치지 않는 완벽한 균형 감각의 소유자!",
        "tags": ["#육각형인재", "#평범함의미학", "#적절함"]
    }
}

def analyze_persona_logic(df: pd.DataFrame) -> Dict[str, Any]:
    """데이터프레임 기반 페르소나 분석 로직"""
    
    # 1. 기본 통계 계산
    total_spent = df[df['type'] == '출금']['amount'].sum()
    if total_spent == 0:
        return PERSONAS["BALANCE"]

    cat_stats = df[df['type'] == '출금'].groupby('category')['amount'].sum()
    cat_ratio = (cat_stats / total_spent * 100).to_dict()
    
    df['hour'] = pd.to_datetime(df['time'], format='%H:%M:%S').dt.hour
    night_spent = df[
        (df['type'] == '출금') & 
        ((df['hour'] >= 22) | (df['hour'] <= 4))
    ]['amount'].sum()
    night_ratio = (night_spent / total_spent * 100) if total_spent > 0 else 0

    store_names = df['store'].astype(str).str
    delivery_count = len(df[store_names.contains("배달|요기요|쿠팡이츠", regex=True)])
    taxi_count = len(df[store_names.contains("택시|카카오T", regex=True)])
    cvs_count = len(df[store_names.contains("GS25|CU|세븐일레븐|이마트24", regex=True)])

    savings_spent = df[
        (df['type'] == '출금') & 
        (df['category'].isin(["저축", "투자", "적금"]))
    ]['amount'].sum()
    savings_ratio = (savings_spent / total_spent * 100)

    # 2. 페르소나 결정 (우선순위 로직)
    # Rule 1: 저축 비중 40% 이상 -> 저축왕
    if savings_ratio >= 40:
        return PERSONAS["SAVER"]
    
    # Rule 2: 야식 비중 20% 이상 or 밤 10시 이후 배달 3회 이상 -> 야식 요정
    if night_ratio >= 20 or (night_ratio > 10 and delivery_count >= 3):
        return PERSONAS["NIGHT_OWL"]
        
    # Rule 3: 카페 비중 25% 이상 -> 카페인 중독
    if cat_ratio.get("카페", 0) >= 25:
        return PERSONAS["CAFE_LOVER"]
        
    # Rule 4: 술/사회 비중 25% 이상 -> 핵인싸
    if cat_ratio.get("사회", 0) >= 25 or cat_ratio.get("술", 0) >= 15:
        return PERSONAS["INSIDER"]
        
    # Rule 5: 쇼핑 비중 30% 이상 -> 쇼퍼홀릭
    if cat_ratio.get("쇼핑", 0) >= 30:
        return PERSONAS["SHOPPER"]
    
    # Rule 6: 택시 5회 이상 -> 택시 귀족
    if taxi_count >= 5:
        return PERSONAS["TAXI_RIDER"]

    # Rule 7: 편의점 10회 이상 -> 편의점 VIP
    if cvs_count >= 10:
        return PERSONAS["CVS_VIP"]

    # Default
    return PERSONAS["BALANCE"]


@mcp_registry_chat.register(
    name="get_financial_persona",
    description="사용자의 소비 패턴을 분석하여 재미있는 '금융 페르소나(별명)'와 특징을 알려줍니다. '내 소비 성향 알려줘', '나 어떤 타입이야?', '소비 MBTI' 등의 질문에 사용합니다."
)
async def get_financial_persona(
    user: User,
    session: Session,
    **kwargs
) -> Dict[str, Any]:
    """
    [MCP Tool] 금융 페르소나 분석
    """
    try:
        if not os.path.exists(DATA_PATH):
            return {"status": "error", "message": "분석할 데이터 파일이 없습니다."}
            
        df = pd.read_json(DATA_PATH)
        
        persona = analyze_persona_logic(df)
        
        return {
            "status": "success",
            "persona": {
                "title": persona["title"],
                "description": persona["desc"],
                "tags": persona["tags"],
                "message": f"회원님의 소비 패턴을 분석한 결과... 당신은 **'{persona['title']}'** 유형입니다!"
            }
        }

    except Exception as e:
        print(f"[Persona Error] {e}")
        return {"status": "error", "message": "페르소나 분석 중 오류가 발생했습니다."}