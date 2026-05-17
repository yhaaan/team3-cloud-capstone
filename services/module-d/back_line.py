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
    answer = "선 그래프 back_line.py 테스트입니다."

    graph = {
        "title": "삼성전자 vs 애플 연도별 매출 비교",
        "labels": {
            "x": "연도",
            "y": "매출(조 원)",
            "name": "기업명"
        },
        "data": [
            {
                "name": "삼성전자",
                "x": [2020, 2021, 2022, 2023, 2024],
                "y": [230, 250, 280, 300, 320]
            },
            {
                "name": "애플",
                "x": [2020, 2021, 2022, 2023, 2024],
                "y": [210, 240, 260, 290, 310]
            },
            {
                "name": "가나",
                "x": [2020, 2021, 2022, 2023, 2024],
                "y": [220, 250, 280, 300, 340]
            }
        ]
    }

    return {
        "answer": answer,
        "how": "line",
        "graph": graph
    }