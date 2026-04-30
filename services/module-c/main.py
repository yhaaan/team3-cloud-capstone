# main.py
from app.agent.graph_agent import GraphAgent
from fastapi import FastAPI
import uuid
from app.schemas import ChatRequest, ChatResponse
from app.config import Config

app = FastAPI()
config = Config()
agent = GraphAgent() 

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    result = agent.run_agent(request.query)
    return ChatResponse(
        final_response=result.final_response,
        relation_graph=result.relation_graph
    )