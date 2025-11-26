from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from backend.database import create_db_and_tables
# DB 테이블 생성용
from backend.models import user

# API 라우터 임포트
from backend.api import user

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

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="My Budget API",
        version="1.0.0",
        routes=app.routes,
    )

    # 전역 Bearer 인증 추가
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    # 기본적으로 모든 API에 Authorization 적용됨
    openapi_schema["security"] = [{"BearerAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# 헬스체크
@app.get("/")
def read_root():
    return {"status": "MCP Server is running ✅"}

# Stub Tool 엔드포인트
@app.post("/tools/analyze_spending")
def analyze_spending():
    return {"message": "Tool stub: analyze_spending()"}

# 라우터 등록
app.include_router(user.router, prefix="/users", tags=["User"])