from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import Optional

from backend.database import get_session
from backend.models.user import User
from backend.api.deps import get_current_user  # ⭐ PR에서 만든 함수 사용
from backend.services.spending.analyze_spending_service import run_spending_analysis_service
from backend.models.analyze_spending import SpendingAnalysis, SpendingCategoryStats

router = APIRouter()

@router.post("/spending")
async def analyze_spending(
    month: Optional[str] = Query(None, description="분석할 월 (예: '10월', '2024-10')"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):  
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
            user=current_user,
            month=month,
            session=session
        )
        
        return {
            "success": True,
            "data": result
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"분석 중 오류가 발생했습니다: {str(e)}"
        )


@router.get("/spending/history")
async def get_analysis_history(
    limit: int = Query(10, ge=1, le=50, description="조회할 개수 (최대 50)"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):    
    try:
        # 사용자의 분석 기록 조회 (최신순)
        statement = select(SpendingAnalysis).where(
            SpendingAnalysis.user_id == current_user.id
        ).order_by(
            SpendingAnalysis.created_at.desc()
        ).limit(limit)
        
        analyses = session.exec(statement).all()
        
        history = []
        for analysis in analyses:
            history.append({
                "id": analysis.id,
                "month": analysis.month,
                "analysis_date": analysis.analysis_date.isoformat(),
                "total_income": analysis.total_income,
                "total_spent": analysis.total_spent,
                "save_potential": analysis.save_potential,
                "top_category": analysis.top_category,
                "overspent_category": analysis.overspent_category,
                "insight_summary": analysis.insight_summary,
                "created_at": analysis.created_at.isoformat()
            })
        
        return {
            "success": True,
            "count": len(history),
            "data": history
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"기록 조회 중 오류가 발생했습니다: {str(e)}"
        )


@router.get("/spending/{analysis_id}")
async def get_analysis_detail(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):    
    try:
        analysis = session.get(SpendingAnalysis, analysis_id)
        
        if not analysis:
            raise HTTPException(status_code=404, detail="분석 기록을 찾을 수 없습니다")
        
        if analysis.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다")
        
        statement = select(SpendingCategoryStats).where(
            SpendingCategoryStats.analysis_id == analysis_id
        ).order_by(SpendingCategoryStats.amount.desc())
        
        category_stats = session.exec(statement).all()
        
        return {
            "success": True,
            "data": {
                "id": analysis.id,
                "month": analysis.month,
                "analysis_date": analysis.analysis_date.isoformat(),
                "total_income": analysis.total_income,
                "total_spent": analysis.total_spent,
                "total_saved": analysis.total_saved,
                "save_potential": analysis.save_potential,
                "daily_average": analysis.daily_average,
                "projected_total": analysis.projected_total,
                "top_category": analysis.top_category,
                "overspent_category": analysis.overspent_category,
                "insight_summary": analysis.insight_summary,
                "insights": analysis.insights,
                "suggestions": analysis.suggestions,
                "chart_data": [
                    {
                        "category_name": stat.category_name,
                        "amount": stat.amount,
                        "count": stat.count,
                        "percent": stat.percent
                    }
                    for stat in category_stats
                ],
                "created_at": analysis.created_at.isoformat()
            }
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"상세 정보 조회 중 오류가 발생했습니다: {str(e)}"
        )