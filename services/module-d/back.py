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

삼성전자를 중심으로 여러 관계가 연결된다고 가정한 테스트 응답입니다.
"""

    graph = {
        "center":"애플",
        "nodes": [
            {
                "id": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:959",
                "name": "삼성전자"
            },
            {
                "id": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:279",
                "name": "인공지능"
            },
            {
                "id": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:1978",
                "name": "삼성전자"
            },
            {
                "id": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:2958",
                "name": "애플"
            }
        ],
        "links": [
            {
                "source": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:959",
                "target": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:279",
                "relation": "BELONGS_TO"
            },
            {
                "source": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:1978",
                "target": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:279",
                "relation": "BELONGS_TO"
            },
            {
                "source": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:1978",
                "target": "4:0ffbdc19-ef92-4b85-9c3e-016e214bc51e:2958",
                "relation": "BELONGS_TO"
            }
        ]
    }

    return {
        "answer": answer,
        "center": True,
        "graph": graph
    }
