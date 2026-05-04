# main.py
from app.agent.graph_agent import GraphAgent
from fastapi import FastAPI
import uuid
from app.schemas import ChatRequest, ChatResponse
from app.config import Config

app = FastAPI()
config = Config()
agent = GraphAgent() 


@app.get("/check-status")
def check_status():
    # 상태가 에러일 때만 재연결을 시도하고 결과를 반환함
    is_ok = agent.retriever.check_connection()
    if not is_ok:
        return {"status": "error", "message": agent.retriever.db_connect_error_msg}
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    result = agent.run_agent(request.query)
    return ChatResponse(
        final_response=result.final_response,
        relation_graph=result.relation_graph
    )