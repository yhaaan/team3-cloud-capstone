# main.py
from langchain_openai import ChatOpenAI
from app.agent.graph_agent import GraphAgent
from fastapi import FastAPI
from app.schemas import ChatRequest, ChatResponse
from app.config import Config
from langchain_core.messages import SystemMessage, HumanMessage


app = FastAPI()
config = Config()
agent = GraphAgent() 

# RAG 사용 안 할 때 답해줄 AI(LLM)
gpt4o = ChatOpenAI(
    model="gpt-4o",
    api_key=Config.OPENAI_API_KEY,
    temperature=0  # 정확도를 위해 0으로 설정
)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    print(f"RAG 사용 여부: {request.rag_on}\n")
    if not request.rag_on:
        # 순수 LLM 모드: 외부 지식 차단
        # DB 조회를 생략하고 빈 컨텍스트를 주거나, 아예 일반 답변 프롬프트를 사용합니다.
        system_prompt = "당신은 기업 분석 전문가입니다. 당신이 기존에 학습한 지식으로만 답변하세요."

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=request.question)
        ]

        # 최종 답변 생성
        response = gpt4o.invoke(messages)

        return ChatResponse(
            answer=response.content,
            has_center=False,
            graph=None
        )

    recent_history_str = get_recent_history_context_str(request.recent_history)
    # 비동기로 변경되었으므로 await 필수
    result = await agent.run_agent(request.question, recent_history_str)
    
    return ChatResponse(
        answer=result.answer,
        has_center=result.has_center,
        graph=result.graph
    )


def get_recent_history_context_str(messages, limit=4):
    """
    messages: DB나 세션에서 가져온 메시지 객체 리스트
    limit: 필터링 후 최종적으로 포함할 메시지 개수 (기본 4개)
    """
    cleaned_messages = []
    
    # 1. 역순으로 검사 (최신 대화부터)
    # 호출 시 현재 질문을 제외하고 싶다면 messages[:-1]을 넣는 것이 좋습니다.
    for msg in reversed(messages):
        # 목표한 개수에 도달하면 즉시 중단
        if len(cleaned_messages) >= limit:
            break
            
        content = msg.get("content", "")
        role = msg.get("role")

        # [필터링] 에러 응답 및 불필요한 HTML 제외
        if role == "assistant":
            if any(err in content for err in ["<html>", "⚠️", "Internal Server Error"]):
                continue # 에러 답변은 무시하고 그 이전 메시지를 더 찾아봄
        
        # 유효한 메시지만 추가
        role_label = "사용자" if role == "user" else "AI"
        cleaned_messages.append(f"{role_label}: {content}")

    # 2. 역순 수집되었으므로 다시 정방향으로 뒤집기
    cleaned_messages.reverse()

    # 3. 문자열로 합치기
    recent_history_str = "\n\n".join(cleaned_messages)
    print(f"[최근 대화 {len(cleaned_messages)}개 추출 완료]\n{recent_history_str}\n")
        
    return recent_history_str