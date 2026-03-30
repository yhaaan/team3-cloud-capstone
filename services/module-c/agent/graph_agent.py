from langgraph.graph import StateGraph
from llm.llm import call_llm
from agent.tools import vector_tool, graph_tool
from typing import TypedDict, List, Any, Annotated
from operator import add # 리스트를 덮어쓰지 않고 '추가'하기 위해 필요
from langgraph.checkpoint.memory import MemorySaver # 메모리 저장소


# 상태 정의
class GraphState(TypedDict):
    query: str
    docs: List[Any]
    graph: Any
    answer: str
    # Annotated와 add를 쓰면, return {"history": [새 메시지]} 할 때 기존 리스트에 합쳐집니다.
    history: Annotated[List[str], add]


# 1. Vector 노드
def vector_node(state: GraphState):
    if state is None:
        return {"docs": []}

    query = state.get("query")
    if not query:
        return {"docs": []} # 쿼리가 없으면 빈 리스트 반환
    
    docs = vector_tool(query)
    return {"docs": docs}


# 2. Graph 노드
def graph_node(state: GraphState):
    query = state.get("query")
    graph_data = graph_tool(query)
    return {"graph": graph_data}


# 3. LLM 노드
def llm_node(state: GraphState):
    # 모든 데이터가 합쳐진 state에서 꺼내 씀
    query = state.get("query", "")
    docs = state.get("docs", [])
    graph = state.get("graph", [])
    history = state.get("history", []) # 이전 대화들

    # 이전 대화 내용을 프롬프트에 포함
    history_str = "\n".join(history[-5:]) # 최근 5개 대화만 참고 (토큰 절약)
    print(history_str)

    context = f"""
    이전 대화: {history_str}
    참고 문서(Docs): {docs}
    그래프 정보(Graph): {graph}
    현재 질문: {query}
    """

    response = call_llm(context)

    print(f"--- LLM RAW RESPONSE: {response} ---")

    # 이번 대화 내용을 history에 추가하여 반환
    current_chat = f"User: {query}\nAI: {response}"
    return {"answer": response, "history": [current_chat]}


# 메모리 저장소 객체 생성 -> 전역 변수
memory = MemorySaver()


# 그래프 구성
def build_graph():
    workflow = StateGraph(GraphState)

    workflow.add_node("rag", vector_node)
    workflow.add_node("graph", graph_node)
    workflow.add_node("llm", llm_node)

    workflow.set_entry_point("rag")

    workflow.add_edge("rag", "graph")
    workflow.add_edge("graph", "llm")

    # 컴파일할 때 checkpointer를 넣어줍니다.
    return workflow.compile(checkpointer=memory)


# 앱도 전역에서 생성
app = build_graph()


# 실행 함수 (config 추가)
def run_agent(query: str, thread_id: str = "default_user"):
    # 어떤 사용자의 대화인지 식별하는 ID (새로고침 전까지 유지될 값)
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {"query": query}
    result = app.invoke(inputs, config=config)

    return result.get("answer", "답변 생성 실패")