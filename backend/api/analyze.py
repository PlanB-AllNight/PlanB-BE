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

@router.get("/compare")
async def get_spending_dashboard(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    소비 분석 대시보드 요약 조회 API

    - 가장 최근 소비 분석 기준
    - 직전 달(예: 11월 기준 10월)의 가장 최신 분석과 비교해 변동률 계산
    - 월별 소비 추이: 각 월별 최신 분석 기준, 최근 6개월
    """

    # 1) 사용자의 가장 최근 소비 분석 1개
    latest = session.exec(
        select(SpendingAnalysis)
        .where(SpendingAnalysis.user_id == current_user.id)
        .order_by(SpendingAnalysis.analysis_date.desc(), SpendingAnalysis.created_at.desc())
    ).first()

    if not latest:
        raise HTTPException(status_code=404, detail="먼저 소비 분석을 한 번 이상 진행해주세요.")

    latest_year, latest_month = map(int, latest.month.split("-"))

    # 2) 직전 달(예: 2025-11 -> 2025-10) 계산
    if latest_month == 1:
        prev_year = latest_year - 1
        prev_month = 12
    else:
        prev_year = latest_year
        prev_month = latest_month - 1

    prev_ym = f"{prev_year:04d}-{prev_month:02d}"

    # 3) 직전 달 중 가장 늦게 한 분석 1개
    prev = session.exec(
        select(SpendingAnalysis)
        .where(SpendingAnalysis.user_id == current_user.id)
        .where(SpendingAnalysis.month == prev_ym)
        .order_by(SpendingAnalysis.created_at.desc())
    ).first()

    # 이번 달 총 소비
    current_total = latest.total_spent

    # 4) 변동률 계산
    change_rate = None
    change_amount = None
    change_direction = None

    if prev:
        prev_total = prev.total_spent
        change_amount = current_total - prev_total

        if prev_total > 0:
            change_rate = round((change_amount / prev_total) * 100)
        else:
            change_rate = None

        if change_amount > 0:
            change_direction = "up"
        elif change_amount < 0:
            change_direction = "down"
        else:
            change_direction = "flat"

    # 5) 이번 달에서 가장 많이 쓴 카테고리 (카테고리 통계 테이블 기준)
    top_category = None

    category_stats = session.exec(
        select(SpendingCategoryStats)
        .where(SpendingCategoryStats.analysis_id == latest.id)
        .order_by(SpendingCategoryStats.amount.desc())
    ).all()

    if category_stats:
        top = category_stats[0]
        top_category = {
            "category": top.category_name,          # 예: "식비"
            "amount": top.amount,              # 예: 450000
            "percent": top.percent,            # 예: 30.0
        }
    
    # 카테고리별 최근 소비 분석
    category_stats_prev = []
    if prev:
        category_stats_prev = session.exec(
            select(SpendingCategoryStats)
            .where(SpendingCategoryStats.spending_analysis_id == prev.id)
        ).all()

    prev_map = {c.category: c for c in category_stats_prev}

    category_analysis = []

    for item in category_stats:
        category = item.category_name
        latest_amount = item.amount
        prev_amount = prev_map.get(category).amount if category in prev_map else 0

        if prev_amount > 0:
            diff_percent = round(((latest_amount - prev_amount) / prev_amount) * 100)
        else:
            diff_percent = None  # 혹은 0

        category_analysis.append({
            "category": category,
            "amount": latest_amount,
            "count": item.count,                       # 해당 카테고리 건수
            "percent": item.percent,                   # 이번 달 비중
            "diff_percent": diff_percent               # 전월 대비 증감률
        })

    # 6) 월별 소비 추이 (각 월별 가장 최신 분석만 사용 → 최근 6개월)
    all_analyses = session.exec(
        select(SpendingAnalysis)
        .where(SpendingAnalysis.user_id == current_user.id)
        .order_by(SpendingAnalysis.analysis_date, SpendingAnalysis.created_at)
    ).all()

    # month_map[YYYY-MM] = 그 달의 가장 최신 분석
    month_map = {}
    for sa in all_analyses:
        ym = sa.month  # "YYYY-MM"
        month_map[ym] = sa  # 동일 키가 오버라이드 → 마지막(가장 최신)만 남음

    # 정렬 후 최근 6개월만
    sorted_ym = sorted(month_map.keys())  # 오름차순
    last_6_ym = sorted_ym[-6:]

    monthly_trend = [
        {
            "month": ym,                          # "2025-06"
            "total_spent": month_map[ym].total_spent,
        }
        for ym in last_6_ym
    ]

    # 7) 응답 형태
    return {
        "success": True,
        "data": {
            "summary": {
                "current_month": latest.month,
                "current_total_spent": current_total,
                "prev_month": prev_ym if prev else None,
                "change_amount": change_amount,        # +300000 같은 값
                "change_rate": change_rate,            # +45 같은 값
                "change_direction": change_direction,  # "up" | "down" | "flat" | None
            },
            "top_category": top_category,
            "monthly_trend": monthly_trend,
            "category_analysis": category_analysis,
        },
    }