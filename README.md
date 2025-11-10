### ⚙️ 로컬 개발 환경 실행 (venv)
1. backend 디렉토리로 이동
    
    ```cd backend```
2. 가상환경 생성 및 실행 (Mac/Linux 기준)
    ```
    python3 -m venv venv
    source venv/bin/activate
    ```
3. 의존성 설치

    ```pip install -r requirements.txt```

4. FastAPI 서버 실행

    ```uvicorn main:app --reload```

### 🐳 Docker 실행 (배포 환경 확인용)
```docker-compose up --build```