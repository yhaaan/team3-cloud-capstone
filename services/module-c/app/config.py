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
    except KeyError as e:
        import sys
        print(f"필수 환경 변수 누락: {e}")
        sys.exit(1)