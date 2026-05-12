import re
from langgraph.graph import StateGraph, END
from app.agent.llm_manager import LLMManager
from app.agent.knowledge_retriever import KnowledgeRetriever
from app.agent.graph_formatter import GraphFormatter
from typing import Any, Dict, Optional, TypedDict, List
from app.schemas import RelationGraph, EntityExtractionData, ChatResponse


# 상태 정의
class GraphState(TypedDict):
    query: str                          # 사용자의 질문
    recent_history_str: str             # 최근 대화 문자열(현재 질문 제외 2쌍(4개) 메시지)
    entities: EntityExtractionData      # 질문에서 추출된 엔티티
    error_msg: str                      # 에러 메시지
    cypher_query: str                   # 생성된 사이퍼 쿼리(그래프 DB 탐색용)
    vector_context: str                 # 벡터 DB 탐색 결과
    graph_context: str                  # 그래프 DB 탐색 결과(llm이 알기 쉽게 관계 하나 하나를 글 형태로 정리)
    graph_structured_data: List[Dict[str, Any]] # 그래프 DB 탐색 결과를 구조화한 데이터(시각화를 위해 노드의 id와 같은 부가 정보 전부 포함된 구조화된 데이터)
    final_response: str                 # 최종 답변
    relation_graph: RelationGraph       # 그래프 DB 탐색 결과 구조화 데이터
    has_center: Optional[bool] = False  # 구조화 데이터 중앙 노드 존재 여부
    center_id: str                    # 구조화 데이터 중앙 노드 이름


class GraphAgent:
    def __init__(self):
        self.llm = LLMManager()
        self.retriever = KnowledgeRetriever()
        self.formatter = GraphFormatter()
        self.app = self._build_graph()


    # 그래프 구성
    def _build_graph(self):
        workflow = StateGraph(GraphState)

        # 노드 등록
        workflow.add_node("rewrite_query", self.rewrite_query)
        workflow.add_node("extract_entity", self.extract_entity)
        workflow.add_node("generate_cypher", self.generate_cypher)
        workflow.add_node("search_databases", self.search_databases)
        workflow.add_node("generate_answer", self.generate_answer)
        workflow.add_node("format_graph", self.format_graph)

        # 진입점 설정
        workflow.set_entry_point("rewrite_query")

        # 엣지 연결
        workflow.add_edge("rewrite_query", "extract_entity")
        workflow.add_edge("generate_cypher", "search_databases")
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
            "search_databases",
            self.check_graph_result,
            {
                "skip_visualization": "generate_answer",    # 바로 최종 답변 생성
                "format_visualization": "format_graph"   # 구조화
            }
        )
        
        return workflow.compile()


    # 실행 함수
    async def run_agent(self, query: str, recent_history_str: str):
        print(f"[LangGraph 실행]\n")
        inputs = {
            "query": query,
            "recent_history_str": recent_history_str
        }
        result = self.app.invoke(inputs)
        return ChatResponse(
            answer=result.get("final_response"),
            has_center=bool(result.get("has_center")),
            graph=result.get("relation_graph")
        )
    

    # 질문 재구성
    def rewrite_query(self, state: GraphState):
        user_query = state.get("query")
        recent_history_str = state.get("recent_history_str")
        
        result = self.llm.rewrite_query(user_query, recent_history_str)

        print("[질문 재구성 완료]")
        print(f"재구성된 질문: {result}\n")
        
        return {
            "query": result
        }
    

    # 엔티티 추출
    def extract_entity(self, state: GraphState):
        user_query = state.get("query")
        recent_history_str = state.get("recent_history_str")
        
        result = self.llm.extract_entities(user_query, recent_history_str)

        print("[엔티티 추출 완료]")
        print(f"추출된 엔티티: {result}\n")

        # 에러 메시지가 있다면 바로 상태에 저장 (다음 노드에서 분기 처리용)
        if result.error_msg:
            return {
                "error_msg": result.error_msg # 에러 메시지만 채워서 반환
            }
        
        refined_entities = self.link_entity(result.data)
        result.data.named_entities.companies = refined_entities.get("companies")
        result.data.named_entities.people = refined_entities.get("people")

        print(f"그래프 DB에 맞게 재정의된 엔티티: {result}\n")
        
        return {
            "entities": result.data,
            "error_msg": None
        }
    

    def link_entity(self, entities: EntityExtractionData):
        # 1. 매핑 정보를 저장할 딕셔너리 생성
        # 예: {"삼성": "삼성전자", "애플": "Apple Inc."}
        name_map = {}

        # 2. 기업(Companies) 정규화 및 매핑 기록
        refined_companies = []
        for original_name in entities.named_entities.companies:
            matched_name = self.retriever.find_best_match(original_name, "Company")
            print(f"원본: {original_name} -> 매칭: {matched_name}\n")

            if matched_name:
                refined_companies.append(matched_name)
                name_map[original_name] = matched_name # 매핑 기록

        # 3. 인물(People) 정규화 및 매핑 기록
        refined_people = []
        for original_name in entities.named_entities.people:
            matched_name = self.retriever.find_best_match(original_name, "Person")
            if matched_name:
                refined_people.append(matched_name)
                name_map[original_name] = matched_name # 매핑 기록

        # 4. [핵심] relation_filters 내부의 이름 업데이트
        # LLM이 뽑아준 subject/object 이름을 정규화된 이름으로 교체합니다.
        if entities.relation_filters:
            for rel in entities.relation_filters:
                # 매핑 사전에 있으면 바꾸고, 없으면 그대로 둠
                rel.subject = name_map.get(rel.subject, rel.subject)
                rel.object = name_map.get(rel.object, rel.object)

        return {
            "companies": refined_companies,
            "people": refined_people
        }


    # 사이퍼 쿼리 생성
    def generate_cypher(self, state: GraphState):
        user_query = state.get("query")
        entities = state.get("entities")
        result = self.llm.generate_cypher(user_query, entities)

        print("[사이퍼 쿼리 생성 완료]")
        print(f"사이퍼 쿼리: {result}\n")

        has_center, center_id = self.extract_center_from_cypher(result)

        return {
            "cypher_query": result,
            "has_center": has_center,
            "center_id": center_id
        }
    

    # 사이퍼 쿼리에서 중앙 노드 추출
    def extract_center_from_cypher(self, cypher_query):
        # n.name 또는 {name: ...} 패턴에서 이름들만 모두 추출
        patterns = [
            r"n\.name\s*=\s*['\"]([^'\"]+)['\"]",
            r"\{\s*name\s*:\s*['\"]([^'\"]+)['\"]"
        ]
        
        found_names = []
        for p in patterns:
            found_names.extend(re.findall(p, cypher_query))
        
        # 중복된 이름이 있을 수 있으니 집합(set)으로 유니크하게 관리
        unique_names = list(set(found_names))

        # [핵심 로직] 정확히 1개일 때만 센터로 인정
        if len(unique_names) == 1:
            return True, unique_names[0]
        
        # 0개이거나 2개 이상이면 무조건 False
        return False, None


    # DB 병렬 탐색
    def search_databases(self, state: GraphState):
        user_query = state.get("query")
        cypher_query = state.get("cypher_query")
        result = self.retriever.get_corporate_context(user_query, cypher_query)
        print("[벡터 컨텍스트]")
        print(f"{result.vector_context}\n")
        return {
            "vector_context": result.vector_context,
            "graph_context": result.graph_db_response.graph_context,
            "graph_structured_data": result.graph_db_response.graph_structured_data,
            "error_msg": result.db_error_msg
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
        recent_history_str = state.get("recent_history_str")

        # 에러가 없으면 정상적으로 LLM 호출
        final_response = self.llm.generate_final_response(
            query=user_query,
            vector_context=vector_context,
            graph_context=graph_context,
            history_context=recent_history_str
        )
        
        return {"final_response": final_response}


    # 그래프 DB 탐색 결과 구조화
    def format_graph(self, state: GraphState):
        graph_structured_data = state.get("graph_structured_data")
        center_name = state.get("center_name")
        result = self.formatter.format_for_visualization(graph_structured_data, center_name)
        print("[구조화된 Relation Graph 결과]\n")
        print(result)
        print('\n')
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
        if not state.get("graph_context") or state["graph_context"] == "":
            return "skip_visualization" # 시각화 건너뛰고 답변 생성으로
        return "format_visualization"   # 구조화 노드로 이동