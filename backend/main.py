from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="PlanB MCP Server",
    description="코스콤 AI Agent Challenge - 대학생 금융 코칭 서버",
    version="1.0.0"
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

# Stub Tool 엔드포인트
@app.post("/tools/analyze_spending")
def analyze_spending():
    return {"message": "Tool stub: analyze_spending()"}