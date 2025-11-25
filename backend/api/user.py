from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from backend.database import get_session
from backend.models.user import User, UserCreate, UserLogin, UserRead
from backend.core.security import get_password_hash, verify_password, create_access_token

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