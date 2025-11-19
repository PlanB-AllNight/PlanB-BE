# PlanB - 대학생 금융 코칭 MCP 서버

코스콤 AI Agent Challenge 2025

## 빠른 시작

### 1. 환경 설정

```bash
# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate    # Windows

# 의존성 설치
cd backend
pip install -r requirements.txt
```

### 2. 서버 실행

```bash
cd backend
uvicorn main:app --reload
```

서버 확인: http://localhost:8000/docs

### 3. 🐳 Docker 실행

```bash
docker compose up --build
```

## 샘플 데이터

- `backend/data/mydata.json`: 3개월 거래 데이터 (샘플)
- `backend/data/generate_mydata.py`: 새 데이터 생성 스크립트

### 새 데이터 생성

```bash
cd backend/data
python3 generate_mydata.py
mv mydata_3months.json mydata.json
```

## 기술 스택

- FastAPI
- Python 3.11
- Pandas
- Docker