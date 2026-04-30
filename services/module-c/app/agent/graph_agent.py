import json
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
from app.agent.llm_manager import LLMManager
from app.agent.knowledge_retriever import KnowledgeRetriever
from app.agent.graph_fromatter import GraphFormatter
from typing import Any, Dict, Optional, TypedDict, List, Annotated
from operator import add # 리스트를 덮어쓰지 않고 '추가'하기 위해 필요
from langgraph.checkpoint.memory import MemorySaver # 메모리 저장소
from app.schemas import RelationGraph, EntityExtractionData, ChatResponse

# 상태 정의
class GraphState(TypedDict):
    query: str                          # 사용자의 질문
    entities: EntityExtractionData      # 질문에서 추출된 엔티티
    error_msg: str                      # 에러 메시지
    cypher_query: str                   # 생성된 사이퍼 쿼리(그래프 DB 탐색용)
    vector_context: str                 # 벡터 DB 탐색 결과
    graph_context: List[Dict[str, Any]] # 그래프 DB 탐색 결과
    final_response: str                 # 최종 답변
    relation_graph: RelationGraph       # 그래프 DB 탐색 결과 구조화 데이터
    # # Annotated와 add를 쓰면, return {"history": [새 메시지]} 할 때 기존 리스트에 합쳐집니다.
    # history: Annotated[List[str], add]


class GraphAgent:
    def __init__(self):
        self.app = self._build_graph()
        self.llm = LLMManager()
        self.retriever = KnowledgeRetriever()
        self.formatter = GraphFormatter()

    # 그래프 구성
    def _build_graph(self):
        workflow = StateGraph(GraphState)

        # 노드 등록
        workflow.add_node("extract_entity", self.extract_entity)
        workflow.add_node("generate_cypher", self.generate_cypher)
        workflow.add_node("serach_databases", self.serach_databases)
        workflow.add_node("generate_answer", self.generate_answer)
        workflow.add_node("format_graph", self.format_graph)

        # 진입점 설정
        workflow.set_entry_point("extract_entity")

        # 엣지 연결
        workflow.add_edge("generate_cypher", "serach_databases")
        workflow.add_edge("format_graph", "generate_answer")
        workflow.add_edge("generate_answer", END)

        # 조건 분기
        workflow.add_conditional_edges(
            "extract_entity",
            self.check_entity_extraction_success,
            {
                "error": "generate_answer",    # 에러 시 바로 최종 답변
                "success": "generate_cypher"   # 성공 시 사이퍼 쿼리 생성
            }
        )

        workflow.add_conditional_edges(
            "serach_databases",
            self.check_graph_result,
            {
                "skip_visualization": "generate_answer",    # 바로 최종 답변 생성
                "format_visualization": "format_graph"   # 구조화
            }
        )
        
        return workflow.compile()


    # 실행 함수
    def run_agent(self, query: str):
        inputs = {"query": query}
        result = self.app.invoke(inputs)
        print("그래프를 실행합니다.")
        return ChatResponse(
            final_response=result.get("final_response"),
            relation_graph=result.get("relation_graph")
        )
    

    # 엔티티 추출
    def extract_entity(self, state: GraphState):
        user_query = state.get("query")
        result = self.llm.extract_entities(user_query)

        print("엔티티 추출이 완료되었습니다.")
        print(result)

        # 에러 메시지가 있다면 바로 상태에 저장 (다음 노드에서 분기 처리용)
        if result.error_msg:
            return {"error_msg": result.error_msg}
        return {
            "entities": result.data
        }
    

    # 사이퍼 쿼리 생성
    def generate_cypher(self, state: GraphState):
        user_query = state.get("query")
        entities = state.get("entities")
        result = self.llm.generate_cypher(user_query, entities)

        print("사이퍼 쿼리 생성이 완료되었습니다.")
        print(result)

        return {
            "cypher_query": result
        }


    # DB 병렬 탐색
    def serach_databases(self, state: GraphState):
        user_query = state.get("query")
        cypher_query = state.get("cypher_query")
        result = self.retriever.get_corporate_context(user_query, cypher_query)
        return {
            "vector_context": result.vector_context,
            "graph_context": result.graph_context
        }
    

    # 최종 답변 생성
    def generate_answer(self, state: GraphState):
        # 이전 단계(추출, 쿼리 실행 등)에서 에러가 있었는지 확인
        error_msg = state.get("error_msg")
        
        # 에러가 있으면 LLM을 거치지 않고 바로 에러 메시지를 최종 답변으로 넣음
        if error_msg:
            return {"final_response": error_msg}
        
        user_query = state.get("query")
        vector_context = state.get("vector_context")
        graph_context = state.get("graph_context")

        # JSON 문자열로 직렬화 (ensure_ascii=False는 한글 깨짐 방지)
        graph_context_json_str = json.dumps(graph_context, indent=2, ensure_ascii=False) 

        # 에러가 없으면 정상적으로 LLM 호출
        answer = self.llm.generate_final_response(
            query=user_query,
            vector_context=vector_context,
            graph_context=graph_context_json_str
        )
        
        return {"final_response": answer}


    # 그래프 DB 탐색 결과 구조화
    def format_graph(self, state: GraphState):
        graph_context = state.get("graph_context")
        result = self.formatter.format_for_visualization(graph_context)
        return {"relation_graph": result}
    

    # 엔티티 추출 성공했는지 판단
    def check_entity_extraction_success(self, state: GraphState):
        # 추출된 엔티티가 없거나 에러가 발생한 경우
        if not state.get("entities") or state.get("error_msg"):
            return "error"
        return "success"


    # 구조화하기에 유효한 그래프 DB 탐색 결과가 있는지 판단
    def check_graph_result(self, state: GraphState):
        # graph_context가 비어있거나 검색 실패(None 문자열 등)인 경우
        if not state.get("graph_context") or state["graph_context"] == "None":
            return "skip_visualization" # 시각화 건너뛰고 답변 생성으로
        return "format_visualization"   # 구조화 노드로 이동