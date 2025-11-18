from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PlanB MCP Server")

# CORS 설정: React 프론트와 연동
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
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