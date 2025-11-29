import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from fastapi import HTTPException
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from backend.models.user import User
from backend.models.analyze_spending import SpendingAnalysis, SpendingCategoryStats
from backend.models.challenge import Challenge, ChallengeStatus, PlanType

from backend.services.spending.analyze_spending import get_current_asset

from backend.ai.services.simulate_ai_service import generate_comprehensive_plans

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_latest_analysis(user_id: int, session: Session) -> Optional[SpendingAnalysis]:
    """사용자의 가장 최근 소비분석 조회"""
    try:
        statement = select(SpendingAnalysis).where(
            SpendingAnalysis.user_id == user_id
        ).order_by(SpendingAnalysis.created_at.desc())
        
        return session.exec(statement).first()
    except Exception as e:
        print(f"최신 소비분석 조회 실패: {e}")
        return None


async def run_challenge_simulation_service(
    user: User,
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: Optional[int],
    monthly_save_potential: Optional[int],
    session: Session
) -> Dict[str, Any]:
    """
    챌린지 시뮬레이션 통합 서비스
    
    프로세스:
    1. 현재 자산 조회 (입력 없으면 자동)
    2. 월 저축 가능액 조회 (입력 없으면 최신 분석에서)
    3. AI 플랜 생성 (generate_comprehensive_plans 호출)
    4. 결과 반환 (DB 저장은 create_challenge API에서)
    """
    
    #  현재 자산 조회
    if current_amount is None:
        current_amount = get_current_asset(user.id) or 0
        print(f"   - 현재 자산: {current_amount:,}원 (자동 조회)")
    else:
        print(f"   - 현재 자산: {current_amount:,}원 (사용자 입력)")
        
    #  월 저축 가능액 조회
    latest_analysis = None
    if monthly_save_potential is None:
        latest_analysis = get_latest_analysis(user.id, session)
        monthly_save_potential = max(0, latest_analysis.save_potential) if latest_analysis else 0
    else:
        latest_analysis = get_latest_analysis(user.id, session)

    #  AI 플랜 생성 서비스 호출
    result = generate_comprehensive_plans(
        event_name=event_name,
        target_amount=target_amount,
        period_months=period_months,
        current_amount=current_amount,
        monthly_save_potential=monthly_save_potential,
        user_name=user.name,
        latest_analysis=latest_analysis,
        session=session
    )
    
    response_data = {
        "event_name": event_name,
        "target_amount": target_amount,
        "current_amount": current_amount,
        "shortfall_amount": max(0, target_amount - current_amount),
        "period_months": period_months,
        "monthly_save_potential": monthly_save_potential,
        
        # generate_comprehensive_plans 결과
        "situation_analysis": result["situation_analysis"],
        "plans": result["plans"],
        "ai_summary": result["ai_summary"],
        "recommendation": result["recommendation"],
        
        "simulation_date": datetime.now().strftime("%Y-%m-%d"),
        "meta": {
            "plans_count": len(result["plans"]),
            "recommended_plans": [p["plan_type"] for p in result["plans"] if p["is_recommended"]],
            "has_latest_analysis": latest_analysis is not None
        }
    }
    
    return response_data


async def create_challenge_with_plan(
    user: User,
    event_name: str,
    target_amount: int,
    period_months: int,
    current_amount: int,
    selected_plan: Dict[str, Any],
    challenge_name: Optional[str],
    session: Session
) -> Dict[str, Any]:
    """
    선택한 플랜으로 챌린지 생성
    """
    
    #  중복 체크 (같은 이벤트로 진행 중인 챌린지)
    statement = select(Challenge).where(
        Challenge.user_id == user.id,
        Challenge.event_name == event_name,
        Challenge.status == ChallengeStatus.IN_PROGRESS
    )
    existing = session.exec(statement).first()
    
    if existing:
        return {
            "id": existing.id,
            "event_name": existing.event_name,
            "plan_title": existing.plan_title,
            "status": existing.status.value,
            "start_date": existing.start_date,
            "end_date": existing.end_date,
            "message": "이미 진행 중인 챌린지가 있습니다.",
            "is_new": False
        }
    
    # challenge_name 자동 생성
    if not challenge_name:
        if current_amount == 0:
            challenge_name = f"0원에서 {event_name} 도전"
        else:
            challenge_name = f"{current_amount:,}원에서 {event_name} 도전"

    latest_analysis = get_latest_analysis(user.id, session)
    
    today = date.today()
    end_date = today + relativedelta(months=period_months)
    
    new_challenge = Challenge(
        user_id=user.id,
        spending_analysis_id=latest_analysis.id if latest_analysis else None,
        
        challenge_name=challenge_name,
        event_name=event_name,
        current_amount=current_amount,
        target_amount=target_amount,
        shortfall_amount=target_amount - current_amount,
        period_months=period_months,
        
        plan_type=PlanType(selected_plan['plan_type']),
        plan_title=selected_plan['plan_title'],
        description=selected_plan['description'],
        monthly_required=selected_plan['monthly_required'],
        monthly_shortfall=selected_plan['monthly_shortfall'],
        final_estimated_asset=selected_plan['final_estimated_asset'],
        expected_period=selected_plan['expected_period'],
        plan_detail=selected_plan.get('plan_detail', {}),
        
        status=ChallengeStatus.IN_PROGRESS,
        start_date=today,
        end_date=end_date
    )
    
    try:
        session.add(new_challenge)
        session.commit()
        session.refresh(new_challenge)
        
        return {
            "id": new_challenge.id,
            "event_name": new_challenge.event_name,
            "plan_title": new_challenge.plan_title,
            "status": new_challenge.status.value,
            "start_date": new_challenge.start_date,
            "end_date": new_challenge.end_date,
            "message": f"'{event_name}' 챌린지가 시작되었습니다!",
            "is_new": True
        }
        
    except Exception as e:
        session.rollback()
        print(f"    DB 저장 실패: {e}")
        print(f"{'='*80}\n")
        raise HTTPException(status_code=500, detail=f"챌린지 생성 실패: {str(e)}")