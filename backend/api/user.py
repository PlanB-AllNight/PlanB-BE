from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from backend.database import get_session
from backend.models.user import User, UserCreate, UserLogin, UserRead
from backend.models.analyze_spending import SpendingAnalysis
from backend.models.budget import BudgetAnalysis
from backend.models.challenge import Challenge, ChallengeStatus
from backend.core.security import get_password_hash, verify_password, create_access_token

from backend.api.deps import get_current_user

router = APIRouter()

# 회원가입
@router.post("/register", response_model=UserRead)
def signup(user: UserCreate, session: Session = Depends(get_session)):
    # 1. 아이디 중복 체크
    existing_user = session.exec(select(User).where(User.userId == user.userId)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 사용 중인 아이디입니다.")
    
    # 2. 전화번호 중복 체크
    existing_phone = session.exec(select(User).where(User.phone == user.phone)).first()
    if existing_phone:
        raise HTTPException(status_code=400, detail="이미 가입된 전화번호입니다.")
    
    # 3. 비밀번호 암호화
    hashed_pw = get_password_hash(user.password)
    
    # 4. DB 저장 (DTO -> Entity 변환)
    db_user = User(
        userId=user.userId,
        password=hashed_pw,
        name=user.name,
        birth=user.birth,
        phone=user.phone
    )
    
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    
    return db_user

# 로그인
@router.post("/login")
def login(user: UserLogin, session: Session = Depends(get_session)):
    db_user = session.exec(select(User).where(User.userId == user.userId)).first()
    
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 틀렸습니다.")
    
    # 토큰 발급
    access_token = create_access_token(data={"sub": str(db_user.id)})
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "id": db_user.id,
            "userId": db_user.userId,
            "name": db_user.name
        }
    }

# 마이 페이지 Summary조회
@router.get("/mypage/summary")
async def get_mypage_summary(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # 최근 소비 분석
    recent_spending = session.exec(
        select(SpendingAnalysis)
        .where(SpendingAnalysis.user_id == current_user.id)
        .order_by(SpendingAnalysis.id.desc())
    ).first()

    # 최근 예산안
    recent_budget = session.exec(
        select(BudgetAnalysis)
        .where(BudgetAnalysis.user_id == current_user.id)
        .order_by(BudgetAnalysis.id.desc())
    ).first()

    if not recent_spending or not recent_budget:
        achievement_rate = None
    else: 
        # 절약 금액 계산
        recommended_total = (
            recent_budget.essential_budget +
            recent_budget.optional_budget +
            recent_budget.saving_budget
        )
        actual_total = recent_spending.total_spent
        saved_amount = max(recommended_total - actual_total, 0)

        # 달성률 계산
        achievement_rate = round((actual_total / recommended_total) * 100)

    # 진행 중 챌린지 개수 (없다면 0)
    ongoing_challenges = session.exec(
        select(Challenge)
        .where(Challenge.user_id == current_user.id)
        .where(Challenge.status == ChallengeStatus.IN_PROGRESS)
    ).all()

    ongoing_challenge_count = len(ongoing_challenges)

    return {
        "success": True,
        "data": {
            "name": current_user.name,
            "saved_amount": saved_amount,
            "achievement_rate": achievement_rate,
            "ongoing_challenges": ongoing_challenge_count
        }
    }