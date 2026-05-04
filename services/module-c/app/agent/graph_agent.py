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
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer


# 상태 정의
class GraphState(TypedDict):
    query: str                          # 사용자의 질문
    entities: EntityExtractionData      # 질문에서 추출된 엔티티
    error_msg: str                      # 에러 메시지
    cypher_query: str                   # 생성된 사이퍼 쿼리(그래프 DB 탐색용)
    vector_context: str                 # 벡터 DB 탐색 결과
    graph_context: str                  # 그래프 DB 탐색 결과(llm이 알기 쉽게 관계 하나 하나를 글 형태로 정리)
    graph_structured_data: List[Dict[str, Any]] # 그래프 DB 탐색 결과를 구조화한 데이터(시각화를 위해 노드의 id와 같은 부가 정보 전부 포함된 구조화된 데이터)
    final_response: str                 # 최종 답변
    relation_graph: RelationGraph       # 그래프 DB 탐색 결과 구조화 데이터
    # # Annotated와 add를 쓰면, return {"history": [새 메시지]} 할 때 기존 리스트에 합쳐집니다.
    # history: Annotated[List[str], add]


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
        print("[LangGraph 실행]\n")
        inputs = {"query": query}
        result = self.app.invoke(inputs)
        return ChatResponse(
            final_response=result.get("final_response"),
            relation_graph=result.get("relation_graph")
        )
    

    # 엔티티 추출
    def extract_entity(self, state: GraphState):
        user_query = state.get("query")
        result = self.llm.extract_entities(user_query)

        print("[엔티티 추출 완료]")
        print(f"추출된 엔티티: {result}\n")

        # 에러 메시지가 있다면 바로 상태에 저장 (다음 노드에서 분기 처리용)
        if result.error_msg:
            return {"error_msg": result.error_msg}
        
        refined_entities = self.link_entity(result.data)
        result.data.named_entities.companies = refined_entities.get("companies")
        result.data.named_entities.people = refined_entities.get("people")

        print(f"그래프 DB에 맞게 재정의된 엔티티: {result}\n")
        
        return {
            "entities": result.data
        }
    

    def link_entity(self, entities: EntityExtractionData):
        # DB에서 미리 가져온 공식 명칭 리스트 (또는 ChromaDB 컬렉션)
        official_companies = self.retriever.company_node_names
        official_people = self.retriever.person_node_names

        # 보정 작업 (List Comprehension)
        refined_companies = [
            self.find_best_match(name, official_companies) 
            for name in entities.named_entities.companies
        ]
        
        refined_people = [
            self.find_best_match(name, official_people) 
            for name in entities.named_entities.people
        ]

        # None(매칭 실패) 제거
        return {
            "companies": [c for c in refined_companies if c],
            "people": [p for p in refined_people if p]
        }
    

    def find_best_match(self, extracted_name, official_names):
        if not extracted_name or not official_names:
            return None

        # 글자 단위(char) n-gram으로 벡터화 (오타나 부분 일치에 강함)
        vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3))
        tfidf_matrix = vectorizer.fit_transform(official_names)
        
        target_vec = vectorizer.transform([extracted_name])
        
        # 모든 공식 명칭과 유사도 비교
        similarities = cosine_similarity(target_vec, tfidf_matrix).flatten()
        best_idx = similarities.argmax()
        
        # 유사도가 0.4(40%) 미만이면 잘못된 추출로 간주
        if similarities[best_idx] < 0.4:
            return None
            
        return official_names[best_idx]


    # 사이퍼 쿼리 생성
    def generate_cypher(self, state: GraphState):
        user_query = state.get("query")
        entities = state.get("entities")
        result = self.llm.generate_cypher(user_query, entities)

        print("[사이퍼 쿼리 생성 완료]")
        print(f"사이퍼 쿼리: {result}\n")

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
        entities = state.get("entities")
        vector_context = state.get("vector_context")
        graph_context = state.get("graph_context")

        # # JSON 문자열로 직렬화 (ensure_ascii=False는 한글 깨짐 방지)
        # graph_context_json_str = json.dumps(graph_context, indent=2, ensure_ascii=False) 

        # 에러가 없으면 정상적으로 LLM 호출
        answer = self.llm.generate_final_response(
            query=user_query,
            entities=entities,
            vector_context=vector_context,
            graph_context=graph_context
        )
        
        return {"final_response": answer}


    # 그래프 DB 탐색 결과 구조화
    def format_graph(self, state: GraphState):
        graph_structured_data = state.get("graph_structured_data")
        result = self.formatter.format_for_visualization(graph_structured_data)
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