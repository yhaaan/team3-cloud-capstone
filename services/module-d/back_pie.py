from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    question: str
    rag_on: bool

@app.post("/chat")
def chat(req: ChatRequest):
    answer = "파이 그래프 테스트입니다."

    graph = {
        "title": "기업별 시장 점유율",
        "labels": ["삼성전자", "애플", "LG전자", "기타"],
        "values": [35, 30, 20, 15]
    }

    return {
        "answer": answer,
        "how": "pie",
        "graph": graph
    }