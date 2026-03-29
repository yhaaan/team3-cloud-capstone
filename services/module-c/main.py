# main.py
from agent.graph_agent import run_agent
from fastapi import Response, Cookie, FastAPI
import uuid

app = FastAPI()

@app.get("/")
def read_root():
    return {"안녕": "FastAPI"}

@app.get("/chat")
def chat(query: str, response: Response, session_id: str = Cookie(None)):
    # 1. 기존 쿠키에 session_id가 없으면 새로 생성
    if session_id is None:
        session_id = str(uuid.uuid4())
        # 2. 브라우저에 쿠키 저장 (세션 종료 전까지 유지)
        response.set_cookie(key="session_id", value=session_id)

    print("session_id: " + session_id) # 디버그용

    # 3. 해당 ID로 에이전트 실행
    # session_id가 같으면 이전 대화를 기억합니다.
    answer = run_agent(query, thread_id=session_id)

    return {"response": answer, "session_id": session_id}