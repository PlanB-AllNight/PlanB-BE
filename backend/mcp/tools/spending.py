from sqlmodel import Session
from backend.mcp.registry import mcp_registry

from backend.models.user import User
from backend.services.spending.analyze_spending_service import run_spending_analysis_service

@mcp_registry.register(
    name="analyze_spending",
    description="사용자의 소비 내역을 분석하여 통계와 인사이트를 제공합니다. 월(month)을 지정하면 해당 월을 분석하며, 지정하지 않거나 해당 월의 데이터가 없는 경우 보유한 데이터 중 가장 최신 월을 분석합니다."
)
async def analyze_spending(
    user: User,
    session: Session,
    month: str = None,
    **kwargs
) -> dict:
    """
    [MCP Tool] 사용자의 소비 내역 분석
    Args:
        month (str): '2024-10' 또는 '10월'. 없으면 최신 데이터 자동 탐색.
    """
    if not month:
        import pandas as pd
        from backend.services.spending.analyze_spending import DATA_PATH
        
        try:
            df = pd.read_json(DATA_PATH)
            df['date'] = pd.to_datetime(df['date'])
            
            # 최신 거래 날짜
            latest_date = df['date'].max()
            month = f"{latest_date.month}월"
            
            print(f"자동 선택된 분석 월: {month} (최신 거래일: {latest_date.date()})")
            
        except Exception as e:
            from datetime import datetime
            now = datetime.now()
            month = f"{now.month}월"
            print(f"mydata 로드 실패, 현재 달로 설정: {month}")
    
    try:
        result = await run_spending_analysis_service(
            user=user,
            month=month,
            session=session
        )
        
        return {
            "status": "success",  # runner가 확인하는 키값
            "meta": {
                "analyzed_month": month,
                "is_auto_detected": False # 혹은 로직에 따라 변수 사용
            },
            "data": result
        }
        
    except Exception as e:
        import traceback
        print(f"🚨 [Tool Error] analyze_spending 내부 오류: {e}")
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e)
        }