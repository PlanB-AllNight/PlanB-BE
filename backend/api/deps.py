from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials 
from jose import jwt, JWTError
from sqlmodel import Session
from backend.database import get_session
from backend.models.user import User
from backend.core.security import SECRET_KEY, ALGORITHM

security = HTTPBearer()

# 현재 로그인한 유저 추출
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    session: Session = Depends(get_session)
) -> User:
    
    # 실제 토큰 문자열 추출
    token = credentials.credentials

    try:
        # 토큰 디코딩
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        
        if user_id is None:
            raise HTTPException(status_code=401, detail="토큰에 사용자 정보가 없습니다.")
            
    except JWTError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    # DB에서 유저 찾기
    user = session.get(User, int(user_id))
    
    if user is None:
        raise HTTPException(status_code=401, detail="유저가 존재하지 않습니다.")
        
    return user

# 현재 로그인한 유저 아이디 추출
def get_current_user_id(
    current_user: User = Depends(get_current_user)
) -> int:
    return current_user.id