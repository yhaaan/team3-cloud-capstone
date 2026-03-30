# main.py
from agent.graph_agent import run_agent
from fastapi import Response, Cookie, FastAPI, Body
import uuid
from pydantic import BaseModel

# 요청 데이터를 정의하는 모델
class ChatRequest(BaseModel):
    query: str
    session_id: str = None

app = FastAPI()


@app.get("/")
def read_root():
    return {"안녕": "FastAPI"}

@app.post("/chat")
async def chat(request: ChatRequest):
    # 1. 클라이언트가 보낸 session_id 확인
    session_id = request.session_id
    
    # 2. 만약 없다면 새로 생성
    if not session_id:
        session_id = str(uuid.uuid4())

    print(f"현재 작업 중인 session_id: {session_id}") # 디버그용

    # 3. LangGraph 에이전트 실행 (thread_id로 세션 구분)
    answer = run_agent(request.query, thread_id=session_id)

    return {
        "answer": answer, 
        "session_id": session_id
    }