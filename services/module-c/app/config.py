import os
from dotenv import load_dotenv

load_dotenv()  # 전역 호출

class Config:
    try:
        # 이 방식은 키가 없으면 바로 KeyError 예외가 발생합니다.
        GEMINI_API_KEY=os.environ["GEMINI_API_KEY"]
        OPENAI_API_KEY=os.environ["OPENAI_API_KEY"]
        NEO4J_URI = os.environ["NEO4J_URI"]
        NEO4J_USER = os.environ["NEO4J_USER"]
        NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
        NEO4J_EX_PASSWORD = os.environ["NEO4J_EX_PASSWORD"]
        
        # --- PostgreSQL 설정 (개별적으로 읽기) ----
        CHAT_HISTORY_DB_HOST = os.environ.get("CHAT_HISTORY_DB_HOST", "localhost")
        CHAT_HISTORY_DB_PORT = os.environ.get("CHAT_HISTORY_DB_PORT", "5432")
        CHAT_HISTORY_DB_USER = os.environ.get("CHAT_HISTORY_DB_USER", "postgres")
        CHAT_HISTORY_DB_PASSWORD = os.environ["CHAT_HISTORY_DB_PASSWORD"] # 비번은 필수이므로 environ[] 사용
        CHAT_HISTORY_DB_NAME = os.environ.get("CHAT_HISTORY_DB_NAME", "postgres")

        # AsyncConnectionPool이 이해할 수 있는 Key-Value 형식으로 조합
        # 이 방식은 특수문자(!)가 포함되어도 파싱 에러가 나지 않습니다.
        CHAT_HISTORY_CONN_INFO = (
            f"host={CHAT_HISTORY_DB_HOST} "
            f"port={CHAT_HISTORY_DB_PORT} "
            f"user={CHAT_HISTORY_DB_USER} "
            f"password={CHAT_HISTORY_DB_PASSWORD} "
            f"dbname={CHAT_HISTORY_DB_NAME}"
        )
    except KeyError as e:
        import sys
        print(f"필수 환경 변수 누락: {e}")
        sys.exit(1)