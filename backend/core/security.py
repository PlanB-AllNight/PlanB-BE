import os

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from jose import jwt, JWTError

from backend.database import get_session
from backend.models.user import User

from dotenv import load_dotenv
from fastapi.security import HTTPBearer

auth_scheme = HTTPBearer()

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 만료시간: 7일

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 비밀번호 해싱 (암호화)
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# 비밀번호 검증
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# JWT 토큰 생성
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# JWT에서 USER 조회
def get_current_user(
    credentials = Depends(auth_scheme),
    session: Session = Depends(get_session)
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user