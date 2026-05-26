import json
import os
from langgraph.graph import StateGraph, END
from app.agent.llm_manager import LLMManager
from app.agent.knowledge_retriever import KnowledgeRetriever
from app.agent.graph_formatter import GraphFormatter
from typing import Annotated, Any, Dict, TypedDict, List
from app.schemas import RelationGraph, EntityExtractionData, ChatResponse, CypherGenerationResponse, SubQuery


# 🌟 1. 리듀서 역할을 할 커스텀 함수를 '먼저' 정의합니다.
def append_context(old_ctx: str, new_ctx: str) -> str:
    # 기존 값이 없으면 새로 들어온 값 리턴
    if not old_ctx:
        return new_ctx
    # 새로 들어온 게 없거나 기본 안내문구면 기존 값 유지
    if not new_ctx or new_ctx == "조회된 벡터 DB 데이터 없음":
        return old_ctx
    # 둘 다 값이 존재하면 구분선과 함께 합치기
    return f"{old_ctx}\n\n=========================================\n\n{new_ctx}"


# 상태 정의
class GraphState(TypedDict):
    query: str                          # 사용자의 질문
    recent_history_str: str             # 최근 대화 문자열(현재 질문 제외 2쌍(4개) 메시지)
    entities: EntityExtractionData      # 질문에서 추출된 엔티티
    pre_normalized_companies: list[str] # 1단계에서 하드코딩 매칭되어 2단계를 건너뛸 기업들을 모아두는 방
    error_msg: str                      # 에러 메시지
    cypher_generation_result: CypherGenerationResponse # 사이퍼 쿼리 생성 결과
    vector_context: Annotated[str, append_context]                 # 벡터 DB 탐색 결과
    graph_context: str                  # 그래프 DB 탐색 결과(llm이 알기 쉽게 관계 하나 하나를 글 형태로 정리)
    graph_structured_data: List[Dict[str, Any]] # 그래프 DB 탐색 결과를 구조화한 데이터(시각화를 위해 노드의 id와 같은 부가 정보 전부 포함된 구조화된 데이터)
    final_response: str                 # 최종 답변
    relation_graph: RelationGraph       # 그래프 DB 탐색 결과 구조화 데이터
    how: str                            # 그래프 종류
    center_id: str                    # 구조화 데이터 중앙 노드 이름
    sub_queries: List[SubQuery]              # Query Planner가 이번 루프에 뽑아낸 하위 질문 리스트
    cypher_query_purposes: str          # 사이퍼 쿼리 목적들 텍스트
    need_history_to_answer: bool        # 현재 질문에 답변하기 위해 이전 기록 맥락이 필요한지 여부


class GraphAgent:
    def __init__(self):
        self.llm = LLMManager()
        self.retriever = KnowledgeRetriever()
        self.formatter = GraphFormatter()
        self.app = self._build_graph()
        self.global_alias_map: Dict[str, Any] = {}
    

    # 그래프 구성
    def _build_graph(self):
        workflow = StateGraph(GraphState)

        # 1. 노드 등록
        workflow.add_node("rewrite_query", self.rewrite_query)              # 질문 재구성
        workflow.add_node("extract_entity", self.extract_entity)            # 엔티티 추출
        workflow.add_node("normalize_entities", self.normalize_entities)    # 엔티티 정규화

        # [병렬 플래닝 구간]
        workflow.add_node("plan_queries", self.plan_queries)                # 벡터 DB용 하위 쿼리 생성
        workflow.add_node("generate_cypher", self.generate_cypher)          # 그래프 DB용 전체 질문 사이퍼 생성

        # 각각 자기 DB만 담당하는 순수한 노드 2개
        workflow.add_node("search_vector_db", self.search_vector_db)      # 🆕 오직 벡터만 탐색
        workflow.add_node("search_graph_db", self.search_graph_db)        # 🆕 오직 그래프만 탐색

        workflow.add_node("format_graph", self.format_graph)                # 시각화 포맷팅
        workflow.add_node("generate_answer", self.generate_answer)          # 최종 답변 생성

        # 2. 진입점 설정
        workflow.set_entry_point("rewrite_query")
        workflow.add_edge("rewrite_query", "extract_entity")
        
        # 3. 다이아몬드 분기 (Parallel Fork)
        workflow.add_edge("normalize_entities", "plan_queries")
        workflow.add_edge("plan_queries", "search_vector_db")
        
        workflow.add_edge("normalize_entities", "generate_cypher")
        workflow.add_edge("generate_cypher", "search_graph_db")
        
        # 4. 합류 및 조건부 분기 (Parallel Join & Conditional Edge)
        
        # 벡터 트랙: 포맷팅이 필요 없으므로 탐색 종료 후 바로 최종 답변 노드로 가서 대기
        workflow.add_edge("search_vector_db", "generate_answer")
        
        # 그래프 트랙: 탐색 종료 후 결과 유무를 체크하여 분기
        workflow.add_conditional_edges(
            "search_graph_db",  # 🌟 주체를 search_databases에서 search_graph_db로 변경
            self.check_graph_result,
            {
                "skip_visualization": "generate_answer",     # 결과 없으면 바로 답변 노드로 합류
                "format_visualization": "format_graph"       # 결과 있으면 포맷팅 노드로 우회
            }
        )
        
        # 포맷팅을 거친 그래프 데이터도 결국 최종 답변 노드로 합류
        workflow.add_edge("format_graph", "generate_answer")
        
        # 5. 최종 종료
        workflow.add_edge("generate_answer", END)

        # 엔티티 에러 체크
        workflow.add_conditional_edges(
            "extract_entity",
            self.check_entity_extraction_success,
            {
                "error": "generate_answer", 
                "success": "normalize_entities"
            }
        )

        return workflow.compile()


    # 실행 함수
    async def run_agent(self, query: str, recent_history_str: str, global_alias_map: Dict[str, Any]):
        print(f"[LangGraph 실행]\n")
        inputs = {
            "query": query,
            "recent_history_str": recent_history_str
        }
        self.global_alias_map = global_alias_map
        result = self.app.invoke(inputs)
        return ChatResponse(
            answer=result.get("final_response"),
            how=result.get("how"),
            graph=result.get("relation_graph")
        )
    

    # 질문 재구성
    def rewrite_query(self, state: GraphState):
        user_query = state.get("query")
        recent_history_str = state.get("recent_history_str")
        
        result = self.llm.rewrite_query(user_query, recent_history_str)

        print("[질문 재구성 완료]")
        print(f"재구성된 질문: {result.rewirtten_query}")
        print(f"need_history_to_answer: {result.need_history_to_answer}\n")
        
        return {
            "query": result.rewirtten_query,
            "need_history_to_answer": result.need_history_to_answer
        }
    

    # 엔티티 추출
    def extract_entity(self, state: GraphState):
        user_query = state.get("query")
        
        # LLM으로부터 EntityExtractionResponse 객체 수신
        result = self.llm.extract_entities(user_query)

        print("[엔티티 추출 완료]")
        print(f"추출된 엔티티: {result}\n")

        # 1. 에러 메시지가 있다면 바로 상태에 저장 (다음 노드에서 분기 처리용)
        if result.error_msg:
            return {
                "error_msg": result.error_msg  # 결격 사유 발생 시 에러만 채워서 탈출
            }
        
        # 2. LLM이 정상 추출한 데이터 꺼내기 (오브젝트가 None일 때를 대비한 Fallback 기본 객체 지정)
        entities = result.named_entities or EntityExtractionData()
        
        return {
            "entities": entities,
            "error_msg": None
        }
    
    
    # 엔티티 정규화
    def normalize_entities(self, state: GraphState):
        entities = state.get("entities")
        normalized_companies = set()
        normalized_groups = set()

        # 1. 기업 매칭: 사전을 찾아 리스트 중 type이 company인 것만 필터링
        for raw_name in getattr(entities, "companies", []):
            meta_list = self.global_alias_map.get(raw_name.upper(), [])
            for meta in meta_list:
                if meta["type"] == "company":
                    normalized_companies.add(meta["official"])

        # 2. 그룹 매칭: 사전을 찾아 리스트 중 type이 group인 것만 필터링
        for raw_name in getattr(entities, "affiliate_groups", []):
            meta_list = self.global_alias_map.get(raw_name.upper(), [])
            for meta in meta_list:
                if meta["type"] == "group":
                    normalized_groups.add(meta["official"])

        entities.companies = list(normalized_companies)
        entities.affiliate_groups = list(normalized_groups)

        print(f"정규화된 엔티티 객체: {entities}\n")

        return {"entities": entities}
    

    def _load_compact_json(self, file_name: str) -> str:
        file_path = f"{self.base_path}/{file_name}"
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return json.dumps(data, ensure_ascii=False)
        return "[]"
    

    # 하위 질문 생성(플랜)
    def plan_queries(self, state: GraphState):
        """
        맥락 복원 및 단문 분해를 수행하는 통합 플래너 노드
        """
        user_query = state.get("query")
        extracted_company_names = state.get("entities").companies
        
        result = self.llm.generate_sub_queries(user_query, extracted_company_names)
        sub_queries = result.sub_queries
        # 필터링 조건을 제외하고 오직 '순수 하위 질문 문자열'만 리스트로 추출
        pure_sub_queries: List[str] = [plan.query for plan in sub_queries]

        print(f"하위 질문 목록: {pure_sub_queries}\n")
        
        return {
            "sub_queries": sub_queries
        }


    # 사이퍼 쿼리 생성
    def generate_cypher(self, state: GraphState):
        user_query = state.get("query")
        entities = state.get("entities")

        result = self.llm.generate_cypher(user_query, entities)

        print("[사이퍼 쿼리 생성 완료]")
        print(f"사이퍼 쿼리 생성 결과: {result}\n")

        return {
            "cypher_generation_result": result
        }


    def search_vector_db(self, state: GraphState):
        sub_queries: List[SubQuery] = state.get("sub_queries", []) or []
        print(f"\n🔎 [벡터 트랙] 총 {len(sub_queries)}개 하위 쿼리 탐색 시작")

        combined_vector_chunks = []

        for idx, plan in enumerate(sub_queries):
            # 깔끔하게 쪼개진 벡터 전용 메서드 호출
            vector_res_text = self.retriever.get_vector_context(
                query=plan.query,
                search_filter=plan.filter
            )
            
            combined_vector_chunks.append(
                f"■ [벡터 검색] 하위 질문 {idx+1}: {plan.query}\n└ 문서 핵심 팩트:\n{vector_res_text}"
            )

        vector_context = "\n\n=========================================\n\n".join(combined_vector_chunks)

        print('[벡터 DB 탐색 결과]')
        print(vector_context)
        print('\n')

        return {"vector_context": vector_context}
    

    def search_graph_db(self, state: GraphState):
        cypher_res: CypherGenerationResponse = state.get("cypher_generation_result")
        cypher_queries = cypher_res.cypher_queries if cypher_res else []
        center_entity_name = cypher_res.center_entity_name if cypher_res else ""

        print(f"\n⚡ [그래프 트랙] 총 {len(cypher_queries)}개 Cypher 쿼리 조회 시작")

        all_graph_structured_data = []
        graph_context_pieces = []
        final_center_id = ""
        formatted_purposes_str = ""

        if cypher_queries:
            # 깔끔하게 쪼개진 그래프 전용 메서드 호출 (가짜 query 문장 필요 없음!)
            g_result = self.retriever.get_graph_context(
                cypher_queries=cypher_queries,
                center_entity_name=center_entity_name
            )

            if g_result:
                if g_result.graph_structured_data:
                    all_graph_structured_data.extend(g_result.graph_structured_data)
                if g_result.center_id:
                    final_center_id = g_result.center_id
                if g_result.graph_context:
                    graph_context_pieces.append(g_result.graph_context)
                if g_result.cypher_query_purposes:
                    formatted_purposes_str = "\n".join([f"* {p}" for p in g_result.cypher_query_purposes])

        graph_context = "\n\n=========================================\n\n".join(graph_context_pieces) if graph_context_pieces else "조회된 그래프 데이터 없음"
        
        print('[그래프 DB 탐색 결과]')
        print(graph_context)
        print('\n')
        

        return {
            "graph_context": graph_context,
            "graph_structured_data": all_graph_structured_data,
            "center_id": final_center_id,
            "cypher_query_purposes": formatted_purposes_str
        }


    # 그래프 DB 탐색 결과 구조화
    def format_graph(self, state: GraphState):
        graph_structured_data = state.get("graph_structured_data")
        center_id = state.get("center_id")
        result = self.formatter.format_for_visualization(graph_structured_data, center_id)
        print("[구조화된 Relation Graph 결과]")
        print(result)
        print('\n')

        # 임시로 그래프 종류 선정(중앙 여부에만 따라 선정)
        if center_id == "":
            how = "network"
        else:
            how = "netcenter"
        
        return {
            "how": how,
            "relation_graph": result
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
        cypher_query_purposes = state.get("cypher_query_purposes", "")

        need_history_to_answer = state.get("need_history_to_answer")
        if need_history_to_answer:
            recent_history_str = state.get("recent_history_str")
        else:
            recent_history_str = ""

        # 에러가 없으면 정상적으로 LLM 호출
        final_response = self.llm.generate_final_response(
            query=user_query,
            vector_context=vector_context,
            graph_context=graph_context,
            cypher_query_purposes=cypher_query_purposes,
            history_context=recent_history_str
        )

        # 🌟 [핵심 수정] cypher_query_purposes를 문자열로 포맷팅하여 final_response 뒤에 붙이기
        if cypher_query_purposes:
            # 기존 답변 맨 아래에 구분선과 함께 추가
            final_response += f"\n\n---\n📊 **연관 그래프 탐색 목적**\n{cypher_query_purposes}"
        
        return {"final_response": final_response}
    

    # 엔티티 추출 성공했는지 판단
    def check_entity_extraction_success(self, state: GraphState):
        # 추출된 엔티티가 없거나 에러가 발생한 경우
        if not state.get("entities") or state.get("error_msg"):
            return "error"
        return "success"
    

    def route_by_turn(self, state: GraphState):
        loop_count = state.get("loop_count", 0)
        if loop_count == 1:
            return "1st_turn_only_vector"
        else:
            return "2nd_turn_parallel"


    # 구조화하기에 유효한 그래프 DB 탐색 결과가 있는지 판단
    def check_graph_result(self, state: GraphState):
        # graph_context가 비어있거나 검색 실패(None 문자열 등)인 경우
        if not state.get("graph_context") or state["graph_context"] == "":
            return "skip_visualization" # 시각화 건너뛰고 답변 생성으로
        return "format_visualization"   # 구조화 노드로 이동