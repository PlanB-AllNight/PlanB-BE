from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

# 1. DB 파일 이름 (이 이름으로 루트 폴더에 파일이 생깁니다)
sqlite_file_name = "planb.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

# 2. 엔진 생성 (Spring의 DataSource)
# connect_args={"check_same_thread": False}는 SQLite를 FastAPI에서 쓸 때 필수 옵션입니다.
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

# 3. 테이블 생성 함수 (Spring의 ddl-auto: update)
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# 4. 세션 주입 함수 (Controller에서 사용할 DB 세션)
def get_session() -> Generator:
    with Session(engine) as session:
        yield session