from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import create_db_and_tables

# DB 테이블 생성용
from backend.models import user, analyze_spending, challenge, budget

# API 라우터 임포트
from backend.api import user, analyze, budget

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    print("DB 테이블 생성 완료!")
    yield

app = FastAPI(
    title="PlanB MCP Server",
    description="코스콤 AI Agent Challenge - 대학생 금융 코칭 서버",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정: React 프론트와 연동
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React 개발 서버
        "http://localhost:5173",  # Vite 사용 시
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 헬스체크
@app.get("/")
def read_root():
    return {"status": "MCP Server is running ✅"}

# 라우터 등록
app.include_router(user.router, prefix="/users", tags=["User"])
app.include_router(analyze.router, prefix="/analyze", tags=["Analyze"])
app.include_router(budget.router, prefix="/budget", tags=["Budget"])
