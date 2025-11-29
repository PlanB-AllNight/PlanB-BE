from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from datetime import date, datetime
from typing import Any, List, Optional
from dateutil.relativedelta import relativedelta

from backend.database import get_session
from backend.api.deps import get_current_user
from backend.models.user import User
from backend.models.analyze_spending import SpendingAnalysis
from backend.models.challenge import (
    Challenge,
    ChallengeInitResponse,
    SimulateRequest,
    SimulateResponse,
    CreateChallengeRequest,
    ChallengeResponse,
    ChallengeStatus,
    PlanType
)
from backend.services.spending.analyze_spending import (
    get_current_asset,
    get_latest_mydata_date
)
from backend.services.simulate.simulate_event_service import (
    run_challenge_simulation_service,
    create_challenge_with_plan
)

router = APIRouter()


def auto_update_challenge_status(challenge: Challenge, session: Session) -> bool:
    """
    챌린지 상태를 자동으로 업데이트합니다.
    
    업데이트 조건:
    1. 진행 중(IN_PROGRESS)인 챌린지만 체크
    2. 종료일(end_date)이 오늘 이전이면 완료 또는 실패 처리
    
    Returns:
        True if updated, False otherwise
    """
    if challenge.status != ChallengeStatus.IN_PROGRESS:
        return False
    
    today = date.today()
    
    if challenge.end_date < today:
        # 목표 달성 여부는 나중에 소비분석과 연계하여 판단
        # 현재는 기간만 체크하여 COMPLETED로 변경
        # TODO: 실제 자산과 목표 금액을 비교하여 COMPLETED/FAILED 판단
        challenge.status = ChallengeStatus.COMPLETED
        challenge.updated_at = datetime.now()
        
        try:
            session.add(challenge)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"자동 완료 처리 실패: {e}")
            return False
    
    return False


#  페이지 초기화 API
@router.get("/init", response_model=ChallengeInitResponse)
async def initialize_challenge_page(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    시뮬레이션 페이지 진입 시 필요한 초기 데이터를 반환합니다.
    
    Returns:
        - current_asset: 현재 보유 자산 (mydata 최신 잔액)
        - monthly_save_potential: 월 저축 가능액 (가장 최근 실행한 소비분석)
        - has_analysis: 소비분석 존재 여부
        - last_analysis_date: 마지막 소비분석 날짜 (YYYY-MM-DD)
        - latest_mydata_date: mydata 최신 거래 날짜 (YYYY-MM-DD)
        - analysis_outdated: 소비분석이 최신 데이터 기준이 아닌지 여부
    
    프론트엔드 로직:
        1. has_analysis == False → "소비분석을 먼저 진행해주세요" 강제
        2. analysis_outdated == True → "최신 데이터로 재분석할까요?" 선택지 제공
        3. 위 두 경우가 아니면 → 시뮬레이션 진행 가능
    """
    
    raw_asset = get_current_asset(current_user.id)
    current_asset = max(0, raw_asset)
    
    latest_mydata_date = get_latest_mydata_date(current_user.id)
    
    statement = select(SpendingAnalysis).where(
        SpendingAnalysis.user_id == current_user.id
    ).order_by(SpendingAnalysis.created_at.desc())
    
    latest_analysis = session.exec(statement).first()
    
    if latest_analysis:
        save_potential = max(0, latest_analysis.save_potential)
        has_analysis = True
        analysis_date_str = latest_analysis.analysis_date.strftime("%Y-%m-%d")
        
        # 최신성 체크 (mydata 날짜 vs 분석 날짜)
        analysis_outdated = False
        if latest_mydata_date and analysis_date_str:
            if latest_mydata_date > analysis_date_str:
                analysis_outdated = True
                
    else:
        save_potential = 0
        has_analysis = False
        analysis_date_str = None
        analysis_outdated = False
    
    return {
        "current_asset": current_asset,
        "monthly_save_potential": save_potential,
        "has_analysis": has_analysis,
        "last_analysis_date": analysis_date_str,
        "latest_mydata_date": latest_mydata_date,
        "analysis_outdated": analysis_outdated
    }


#  시뮬레이션 실행 API (AI Service 사용)
@router.post("/simulate", response_model=SimulateResponse)
async def run_simulation(
    request: SimulateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
) -> Any:
    """
    시뮬레이션을 실행하고 AI가 생성한 맞춤형 플랜을 반환합니다.
    
    Request:
        - event_name: 이벤트 이름 (필수)
        - target_amount: 목표 금액 (필수)
        - period: 목표 기간(개월) (필수)
        - current_asset: 현재 보유 자산 (선택, 없으면 mydata에서 자동 조회)
        - monthly_save_potential: 월 저축 가능액 (선택, 없으면 소비분석에서 자동 조회)
    
    Response:
        AI가 생성한 맞춤형 플랜들 (situation_analysis, plans, ai_summary, recommendation 포함)
    """
    
    try:
        result = await run_challenge_simulation_service(
            user=current_user,
            event_name=request.event_name,
            target_amount=request.target_amount,
            period_months=request.period,
            current_amount=request.current_asset,
            monthly_save_potential=request.monthly_save_potential,
            session=session
        )
        
        return result
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"시뮬레이션 중 오류가 발생했습니다: {str(e)}"
        )


#  챌린지 생성 API (AI Service 사용)
@router.post("/", response_model=ChallengeResponse)
async def create_challenge(
    request: CreateChallengeRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
) -> Any:
    """
    선택한 플랜으로 챌린지를 생성합니다.
    
    중복 방지 로직:
        같은 유저가 같은 이벤트 + 같은 현재 금액 + 같은 플랜으로
        진행 중인 챌린지가 있으면 새로 생성하지 않고 기존 챌린지 반환
    
    종료일 계산:
        목표 기간(period_months)을 기준으로 계산
        (예상 기간이 아닌 사용자가 설정한 목표 기간)
    """
    
    try:
        # 플랜 데이터 변환 (Request → Dict)
        selected_plan = {
            "plan_type": request.plan_type.value,
            "plan_title": request.plan_title,
            "description": request.description,
            "monthly_required": request.monthly_required,
            "monthly_shortfall": request.monthly_shortfall,
            "final_estimated_asset": request.final_estimated_asset,
            "expected_period": request.expected_period,
            "plan_detail": request.plan_detail
        }
        
        result = await create_challenge_with_plan(
            user=current_user,
            event_name=request.event_name,
            target_amount=request.target_amount,
            period_months=request.period_months,
            current_amount=request.current_amount,
            selected_plan=selected_plan,
            challenge_name=request.challenge_name,
            session=session
        )
        
        return result
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"챌린지 생성 중 오류가 발생했습니다: {str(e)}"
        )


#  내 챌린지 목록 조회 API
@router.get("/my", response_model=List[Challenge])
async def get_my_challenges(
    status: Optional[ChallengeStatus] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    내 챌린지 목록을 조회합니다.
    
    Query Parameters:
        - status: 챌린지 상태 필터 (선택)
          예: ?status=IN_PROGRESS (진행 중만 보기)
    
    Returns:
        최신순으로 정렬된 챌린지 목록
    """
    statement = select(Challenge).where(
        Challenge.user_id == current_user.id
    )
    
    if status:
        statement = statement.where(Challenge.status == status)
    
    statement = statement.order_by(Challenge.created_at.desc())
    
    challenges = session.exec(statement).all()

    for challenge in challenges:
        auto_update_challenge_status(challenge, session)
    
    challenges = session.exec(statement).all()

    return challenges


#  챌린지 상세 조회 API
@router.get("/{challenge_id}", response_model=Challenge)
async def get_challenge_detail(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    특정 챌린지의 상세 정보를 조회합니다.
    """
    statement = select(Challenge).where(
        Challenge.id == challenge_id,
        Challenge.user_id == current_user.id
    )
    
    challenge = session.exec(statement).first()
    
    if not challenge:
        raise HTTPException(status_code=404, detail="챌린지를 찾을 수 없습니다.")
    
    auto_update_challenge_status(challenge, session)
    session.refresh(challenge)
    
    return challenge


#  챌린지 상태 업데이트 API
@router.patch("/{challenge_id}/status")
async def update_challenge_status(
    challenge_id: int,
    new_status: ChallengeStatus,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    챌린지 상태를 업데이트합니다.
    
    사용 예:
        - 사용자가 포기: IN_PROGRESS → FAILED
        - 목표 달성: IN_PROGRESS → COMPLETED
    
    Note:
        자동 완료 처리는 배치 작업이나 다음 소비분석 시 처리
    """
    statement = select(Challenge).where(
        Challenge.id == challenge_id,
        Challenge.user_id == current_user.id
    )
    
    challenge = session.exec(statement).first()
    
    if not challenge:
        raise HTTPException(status_code=404, detail="챌린지를 찾을 수 없습니다.")
    
    challenge.status = new_status
    challenge.updated_at = datetime.now()
    
    try:
        session.add(challenge)
        session.commit()
        session.refresh(challenge)
        
        return {
            "id": challenge.id,
            "status": challenge.status.value,
            "message": f"챌린지 상태가 '{new_status.value}'로 변경되었습니다."
        }
        
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"상태 업데이트 실패: {str(e)}")