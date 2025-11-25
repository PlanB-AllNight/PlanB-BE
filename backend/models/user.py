from typing import Optional
from sqlmodel import Field, SQLModel
from datetime import datetime

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    userId: str = Field(unique=True, index=True) # 아이디
    password: str  # 암호화된 비밀번호 저장
    name: str
    birth: str
    phone: str
    created_at: datetime = Field(default_factory=datetime.now)

# 회원가입용 DTO
class UserCreate(SQLModel):
    userId: str
    password: str
    name: str
    birth: str
    phone: str

# 로그인용 DTO
class UserLogin(SQLModel):
    userId: str
    password: str

# 응답용 DTO (비밀번호 제외)
class UserRead(SQLModel):
    id: int
    userId: str
    name: str
    birth: str
    phone: str
    created_at: datetime