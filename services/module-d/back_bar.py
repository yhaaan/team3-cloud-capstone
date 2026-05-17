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
    answer = "막대 그래프 테스트입니다."

    graph = {
        "title": "기업별 매출 비교",
        "labels": {
            "x": "기업명",
            "y": "매출(조 원)"
        },
        "x": ["삼성전자", "애플", "LG전자", "기타"],
        "y": [320, 310, 90, 60]
    }

    return {
        "answer": answer,
        "how": "bar",
        "graph": graph
    }