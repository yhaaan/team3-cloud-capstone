# main.py
from app.agent.graph_agent import GraphAgent
from fastapi import FastAPI
import uuid
from app.schemas import ChatRequest, ChatResponse
from app.config import Config
from contextlib import asynccontextmanager


# 1. 서버 시작/종료 시 관리를 위한 lifespan (최신 방식)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작할 때 에러가 나도 서버는 켜지도록 예외 처리
    try:
        await agent.initialize()
    except Exception as e:
        print(f"서버 초기화 중 오류 발생: {e}")
        # agent 내부에 에러 상태를 저장해두면 나중에 체크하기 좋아요
        agent.init_error = str(e) 
    yield
    if agent.pool:
        await agent.pool.close()


app = FastAPI(lifespan=lifespan)
config = Config()
agent = GraphAgent() 


@app.get("/check-status")
def check_status():
    # 초기화 중 에러가 있었는지 확인
    init_error = getattr(agent, 'init_error', None)
    if init_error:
        return {"status": "error", "message": f"초기화 실패: {agent.init_error}"}
    
    # 기존 리트리버 체크 + 도커 DB(Pool) 상태도 함께 체크하면 더 완벽합니다.
    is_retriever_ok = agent.retriever.check_connection()
    is_docker_db_ok = agent.pool is not None and not agent.pool.closed
    
    if not is_retriever_ok:
        return {"status": "error", "message": agent.retriever.db_connect_error_msg}
    if not is_docker_db_ok:
        return {"status": "error", "message": "도커 PostgreSQL 연결에 실패했습니다."}
        
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # session_id(thread_id)를 함께 넘겨줘야 기록이 남습니다.
    # 만약 request에 session_id가 없다면 임시로 "default_user" 등을 넣으세요.
    session_id = getattr(request, "session_id", "default_session")
    
    # 비동기로 변경되었으므로 await 필수
    result = await agent.run_agent(request.query, session_id)
    
    return ChatResponse(
        final_response=result.final_response,
        relation_graph=result.relation_graph
    )