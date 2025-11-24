from datetime import datetime, timedelta
from passlib.context import CryptContext
# 설정 (나중에 .env로)
SECRET_KEY = "planb-secret-key-change-me" # 아무 문자열이나 길게
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 만료시간: 7일

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 비밀번호 해싱 (암호화)
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)