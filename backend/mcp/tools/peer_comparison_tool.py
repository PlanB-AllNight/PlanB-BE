import json
from datetime import datetime
from typing import Dict, Any
from sqlalchemy import func
from sqlmodel import Session, select
from backend.mcp.registry.mcp_registry_chat import mcp_registry_chat
from backend.models.user import User
from backend.models.analyze_spending import SpendingAnalysis, SpendingCategoryStats

FALLBACK_STATS = {
    "전체": 990000,
    "식사": 400000,
    "카페/디저트": 90000,
    "쇼핑/꾸미기": 150000,
    "교통": 70000,
    "술/유흥": 100000,
    "주거": 480000,
    "통신/구독": 65000,
    "저축/투자": 100000,
    "교육/학습": 50000
}

def calculate_age(birth_str: str) -> int:
    """생년월일 문자열에서 만 나이 계산"""
    try:
        # 형식: YYYY-MM-DD or YYYYMMDD
        birth_year = int(birth_str[:4])
        current_year = datetime.now().year
        return current_year - birth_year
    except:
        return 22

def normalize_category(query_category: str) -> str:
    """사용자의 자연어 카테고리를 시스템 카테고리로 매핑"""
    if not query_category:
        return "전체"
    
    map_dict = {
        "식사": "식사",
        "교통": "교통",
        "주거": "주거",
        "통신": "통신/구독",
        "쇼핑": "쇼핑/꾸미기",
        "카페": "카페/디저트",
        "술": "술/유흥",
        "교육": "교육/학습",
        "저축": "저축/투자",
        "투자": "저축/투자",

        "밥": "식사", "식비": "식사", "편의점": "식사",
        "커피": "카페/디저트", "카페": "카페/디저트", "디저트": "카페/디저트",
        "옷": "쇼핑/꾸미기", "쇼핑": "쇼핑/꾸미기", "화장품": "쇼핑/꾸미기",
        "버스": "교통", "지하철": "교통", "택시": "교통",
        "술": "술/유흥", "회식": "술/유흥",
        "집": "주거", "월세": "주거",
        "폰": "통신/구독", "넷플릭스": "통신/구독"
    }
    if query_category in map_dict:
        return map_dict[query_category]
    
    for key, val in map_dict.items():
        if key in query_category:
            return val
    return "전체"

def get_real_peer_average(session: Session, category: str, age: int) -> int:
    """
    [핵심] DB에서 실제 사용자들의 해당 카테고리 평균 지출액을 계산합니다.
    """
    try:
        current_year = datetime.now().year
        birth_year = current_year - age

        start_year_prefix = str(birth_year - 2)
        end_year_prefix = str(birth_year + 2)

        avg_val = 0

        if category == "전체":
            statement = (
                select(func.avg(SpendingAnalysis.total_spent))
                .join(User, SpendingAnalysis.user_id == User.id)
                .where(User.birth >= start_year_prefix)
                .where(User.birth <= end_year_prefix + "1231")
            )

            count_stmt = (
                select(func.count(SpendingAnalysis.id))
                .join(User, SpendingAnalysis.user_id == User.id)
                .where(User.birth >= start_year_prefix)
                .where(User.birth <= end_year_prefix + "1231")
            )
            count = session.exec(count_stmt).one()

            if count <= 2:
                return 0
            
            avg_val = session.exec(statement).first()
        else:
            statement = (
                select(func.avg(SpendingCategoryStats.amount))
                .join(SpendingAnalysis, SpendingCategoryStats.analysis_id == SpendingAnalysis.id)
                .join(User, SpendingAnalysis.user_id == User.id)
                .where(SpendingCategoryStats.category_name == category)
                .where(User.birth >= start_year_prefix)
                .where(User.birth <= end_year_prefix + "1231")
            )

            count_stmt = (
                select(func.count(SpendingCategoryStats.id))
                .join(SpendingAnalysis, SpendingCategoryStats.analysis_id == SpendingAnalysis.id)
                .join(User, SpendingAnalysis.user_id == User.id)
                .where(SpendingCategoryStats.category_name == category)
                .where(User.birth >= start_year_prefix)
                .where(User.birth <= end_year_prefix + "1231")
            )
            count = session.exec(count_stmt).one()

            if count <= 2:
                return 0
            
            avg_val = session.exec(statement).first()
            
        return int(avg_val) if avg_val else 0
        
    except Exception as e:
        print(f"[DB Average Error] {e}")
        return 0

@mcp_registry_chat.register(
    name="compare_with_peers",
    description="나의 소비를 또래(평균)와 비교합니다. '나 식비 많이 써?', '남들은 얼마나 써?', '평균이랑 비교해줘' 등의 질문에 사용합니다."
)
async def compare_with_peers(
    user: User,
    session: Session,
    category: str = "전체"
) -> Dict[str, Any]:
    """
    [MCP Tool] 또래 소비 비교 분석
    """
    #  사용자 데이터 조회 (최신 분석)
    my_analysis = session.exec(
        select(SpendingAnalysis)
        .where(SpendingAnalysis.user_id == user.id)
        .order_by(SpendingAnalysis.created_at.desc())
    ).first()

    if not my_analysis:
        return {
            "status": "error",
            "message": "비교할 내 소비 데이터가 없어요! 먼저 [소비 분석]을 진행해주세요."
        }

    #  카테고리 매핑 및 내 지출액 찾기
    target_category = normalize_category(category)
    my_amount = 0
    
    if target_category == "전체":
        my_amount = my_analysis.total_spent
    else:
        for stat in my_analysis.category_stats:
            if stat.category_name == target_category:
                my_amount = stat.amount
                break
    
    #  또래 평균 데이터 가져오기
    age = calculate_age(user.birth)
    peer_avg = get_real_peer_average(session, target_category, age)

    if peer_avg == 0:
        peer_avg = FALLBACK_STATS.get(target_category, 100000)
        print(f"   -> DB 데이터 부족으로 기본 통계값 사용: {peer_avg}")
    else:
        print(f"   -> DB 실시간 평균값 조회 성공: {peer_avg}")

    #  비교 분석 로직
    diff = my_amount - peer_avg
    percent = int((my_amount / peer_avg) * 100) if peer_avg > 0 else 0

    status_label = ""
    status_color = "" # 프론트엔드 참고용 (success, warning, danger)
    message = ""

    if percent >= 150:
        status_label = "🚨 과소비 경보"
        status_color = "danger"
        message = f"또래 평균보다 {abs(diff):,}원이나 더 쓰고 계시네요! 줄일 필요가 있어요."
    elif percent >= 110:
        status_label = "⚠️ 주의 필요"
        status_color = "warning"
        message = f"평균보다 조금({abs(diff):,}원) 더 쓰셨어요. 조금만 신경 써볼까요?"
    elif percent >= 80:
        status_label = "✅ 평균 수준"
        status_color = "success"
        message = "남들과 비슷하게 아주 적절하게 쓰고 계시네요!"
    else:
        status_label = "👏 절약 고수"
        status_color = "primary"
        message = f"와우! 평균보다 {abs(diff):,}원이나 아끼셨어요. 저축왕 유망주입니다!"

    if target_category == "전체":
        message += "\n\n(Tip: '식비 비교해줘'처럼 궁금한 항목을 콕 집어 말하면 더 정확하게 비교해드려요!)"

    return {
        "status": "success",
        "comparison": {
            "title": f"{age}세 또래와의 {target_category} 소비 비교",
            "category": target_category,
            "my_amount": my_amount,
            "peer_avg": peer_avg,
            "diff": diff,
            "percent": percent,
            "status_label": status_label,
            "status_color": status_color,
            "message": message,
            "chart_data": [
                {"label": "나", "value": my_amount},
                {"label": "또래 평균", "value": peer_avg}
            ]
        }
    }