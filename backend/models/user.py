from typing import Optional
from pydantic import BaseModel
from sqlmodel import Field, SQLModel
from datetime import datetime

class User(SQLModel, table=True):
    __tablename__ = "user"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    userId: str = Field(unique=True, index=True) # 아이디
    password: str  # 암호화된 비밀번호 저장
    name: str
    birth: str
    phone: str
    created_at: datetime = Field(default_factory=datetime.now)

# 회원가입용 DTO
class UserCreate(BaseModel):
    userId: str
    password: str
    name: str
    birth: str
    phone: str

# 로그인용 DTO
class UserLogin(BaseModel):
    userId: str
    password: str

# 응답용 DTO (비밀번호 제외)
class UserRead(BaseModel):
    id: int
    userId: str
    name: str
    birth: str
    phone: str
    created_at: datetime