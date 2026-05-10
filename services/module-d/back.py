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
    answer = f"""
삼성전자 중심 관계 분석 결과입니다.
삼성전자를 중심으로 A회사, B회사, C회사, D회사가 각각 지분 관계를 가진다고 가정한 테스트 응답입니다.

- A회사: 삼성전자 지분 35%
- B회사: 삼성전자 지분 30%
- C회사: 삼성전자 지분 10%
- D회사: 삼성전자 지분 25%
"""
    graph = {
        "center": "삼성전자",
        "nodes": [
            {"id": "A회사", "label": "A회사", "share": 35},
            {"id": "B회사", "label": "B회사", "share": 30},
            {"id": "C회사", "label": "C회사", "share": 10},
            {"id": "D회사", "label": "D회사", "share": 25}
        ],
        "edges": [
            {"from": "A회사", "to": "삼성전자", "label": "35%", "share": 35},
            {"from": "B회사", "to": "삼성전자", "label": "30%", "share": 30},
            {"from": "C회사", "to": "삼성전자", "label": "10%", "share": 10},
            {"from": "D회사", "to": "삼성전자", "label": "25%", "share": 25}
        ]
    }

    return {
        "answer": answer,
        "graph": graph
    }