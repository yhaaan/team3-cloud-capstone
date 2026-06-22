# main.py
import asyncio
import json
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from app.agent.graph_agent import GraphAgent
from fastapi import FastAPI
from app.schemas import ChatRequest, ChatResponse
from app.config import Config
from langchain_core.messages import SystemMessage, HumanMessage
from contextlib import asynccontextmanager


GLOBAL_ALIAS_MAP = {}

# 1. 수명 주기(Lifespan)를 관리하는 컨텍스트 매니저 정의
@asynccontextmanager
async def lifespan(app: FastAPI):
    # [STARTUP] 서버가 시작될 때 실행될 로직
    global GLOBAL_ALIAS_MAP
    print("🚀 수명 주기 시작: 에일리어스 사전을 로드합니다.")
    # 초기화: { "카카오": [ {meta1}, {meta2} ] } 형태가 되도록 설정
    GLOBAL_ALIAS_MAP = {}

    # 헬퍼 함수: 딕셔너리 키에 리스트가 없으면 만들고 추가
    def add_to_map(key, meta):
        if key not in GLOBAL_ALIAS_MAP:
            GLOBAL_ALIAS_MAP[key] = []
        GLOBAL_ALIAS_MAP[key].append(meta)
    
    file_paths = ["master_aliases.json"]
    for path in file_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                alias_data = json.load(f)
            
            for item in alias_data:
                official_name = item["official"]
                meta_info = {"official": official_name, "type": item["type"]}
                
                # 공식명 및 별칭들을 키로 등록
                keys_to_register = [official_name, official_name.upper()] + item["aliases"] + [a.upper() for a in item["aliases"]]
                
                for k in set(keys_to_register): # set으로 중복 키 등록 방지
                    add_to_map(k, meta_info)
        except FileNotFoundError:
            print(f"⚠️ {path} 파일이 없습니다.")

    # 이 시점에서 FastAPI가 컨텍스트를 유지하며 요청을 받기 시작합니다.
    yield
    
    # [SHUTDOWN] 서버가 종료될 때 실행될 로직
    print("🛑 수명 주기 종료: 글로벌 메모리를 정리하거나 커넥션을 닫습니다.")
    GLOBAL_ALIAS_MAP.clear()


app = FastAPI(lifespan=lifespan)
config = Config()
agent = GraphAgent() 


# RAG 사용 안 할 때 답해줄 AI(LLM)
gpt4o = ChatOpenAI(
    model="gpt-4o",
    api_key=Config.OPENAI_API_KEY,
    temperature=0  # 정확도를 위해 0으로 설정
)


@app.post("/chat")
async def chat(request: ChatRequest):
    print(f"RAG 사용 여부: {request.rag_on}\n")

    async def event_generator():
        if not request.rag_on:
            # 순수 LLM 모드: 외부 지식 차단
            # DB 조회를 생략하고 빈 컨텍스트를 주거나, 아예 일반 답변 프롬프트를 사용합니다.
            system_prompt = "당신은 기업 분석 전문가입니다. 당신이 기존에 학습한 지식으로만 답변하세요."

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=request.question)
            ]

            # 🚀 Streamlit의 로딩바 문구 유지를 위해 '상태 정보' 하나를 던져줍니다.
            yield json.dumps({"type": "status", "content": "🤖 순수 LLM 지식으로 답변을 작성하고 있습니다..."}) + "\n"

            # 최종 답변 생성
            response = await gpt4o.ainvoke(messages)

            # 프론트엔드가 파싱하기 쉽게 형식을 통일하여 던집니다.
            yield json.dumps({"type": "answer", "content": response.content}) + "\n"
            return
        
        # --- [경우 2] GraphRAG 모드 (RAG ON) ---
        recent_history_str = get_recent_history_context_str(request.recent_history)
        
        # LangGraph 인풋 구조
        inputs = {
            "query": request.question,
            "recent_history_str": recent_history_str
        }

        # 🚀 기존 방식처럼 클래스 내부 변수에 직접 사전을 심어줍니다.
        agent.global_alias_map = GLOBAL_ALIAS_MAP

        # 🚀 최종 상태 값을 담아둘 그릇을 미리 준비합니다.
        last_state_values = {}

        # 🚀 LangGraph의 실시간 노드 업데이트 이벤트를 스트리밍합니다.
        async for update_chunk in agent.app.astream(inputs, stream_mode="updates"):
            if not update_chunk:
                continue
            
            node_name = list(update_chunk.keys())[0]
            
            # 🚀 핵심 수정: 이전 노드가 만들어둔 값을 유지하면서 새 노드의 값을 누적(merge)합니다.
            # 이래야 이전 노드가 만든 relation_graph와 마지막 노드가 만든 final_response가 공존합니다.
            if isinstance(update_chunk[node_name], dict):
                last_state_values.update(update_chunk[node_name])
            
            # 현재 통과 중인 노드별로 상태 메시지를 매칭합니다.
            if node_name == "rewrite_query":
                status_message = "🔍 유저 질문의 의도를 분석하고 재구성하는 중..."
            elif node_name == "extract_entity":
                status_message = "🏷️ 질문에서 주요 기업 및 핵심 분석 키워드를 추출 중..."
            elif node_name == "normalize_entities":
                status_message = "⚙️ 추출한 엔티티 정규화 중..."
            elif node_name == "plan_queries" or node_name == "generate_cypher":
                status_message = "🗺️ 질문 맥락 기반의 다각도 기업 정보 추적 경로 구성 중..."
            elif node_name == "search_vector_db" or node_name == "search_graph_db":
                status_message = "⚡ 기업 공시 및 복합 관계망 데이터 동시 분석 중..."
            elif node_name == "format_graph":
                status_message = "📊 탐색된 지식 그래프를 시각화 형태로 가공하는 중..."
            elif node_name == "generate_answer":
                status_message = "✍️ 수집된 모든 맥락을 종합하여 분석 리포트 작성 중..."
            
            if status_message:
                yield json.dumps({"type": "status", "content": status_message}) + "\n"
                await asyncio.sleep(0.01) # 이벤트를 스무스하게 밀어주기 위한 미세 딜레이

        # # 모든 노드 처리가 끝나면 최신 메모리(State)에서 결과물을 컴파일하여 최종 반환
        # final_state = await agent.app.aget_state(inputs)
        # state_values = final_state.values if final_state else {}

        # 🚀 대신 루프에서 끝까지 갱신된 last_state_values를 바로 사용합니다.
        try:
            validated_response = ChatResponse(
                answer=last_state_values.get("final_response", "답변 생성에 실패했습니다."),
                how=last_state_values.get("how", ""),
                graph=last_state_values.get("relation_graph", None)
            )
        except Exception as e:
            print(f"[🚨 SPEC ERROR] ChatResponse 규격 검증 실패: {e}")
            validated_response = ChatResponse(
                answer="시스템 내부 데이터 규격 오류가 발생했습니다.",
                how="",
                graph=None
            )

        # 기존 ChatResponse 스펙 규격에 맞춰 딕셔너리로 전송
        final_data = {
            "type": "answer",
            "content": validated_response.model_dump()
        }

        yield json.dumps(final_data) + "\n"

    # StreamingResponse로 랩핑하여 한 줄씩 실시간 전달
    return StreamingResponse(event_generator(), media_type="application/json")


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


# 엔티티 추출 로직 (동일)
def extract_normalized_entities(user_query: str):
    detected_entities = {}
    clean_query = user_query.replace(" ", "").lower()
    sorted_keys = sorted(GLOBAL_ALIAS_MAP.keys(), key=len, reverse=True)
    
    for alias_key in sorted_keys:
        clean_key = alias_key.replace(" ", "").lower()
        if clean_key and clean_key in clean_query:
            meta = GLOBAL_ALIAS_MAP[alias_key]
            detected_entities[meta["official"]] = {
                "official": meta["official"],
                "type": meta["type"]
            }
            clean_query = clean_query.replace(clean_key, " ")
            
    return list(detected_entities.values())


@app.get("/search")
def search_governance(query: str):
    matched_results = extract_normalized_entities(query)
    return {"status": "success", "matched": matched_results}