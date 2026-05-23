import json
import os
import re
from langgraph.graph import StateGraph, END
from app.agent.llm_manager import LLMManager
from app.agent.knowledge_retriever import KnowledgeRetriever
from app.agent.graph_formatter import GraphFormatter
from typing import Annotated, Any, Dict, Optional, TypedDict, List
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
    # has_center: Optional[bool] = False  # 구조화 데이터 중앙 노드 존재 여부
    center_id: str                    # 구조화 데이터 중앙 노드 이름
    sub_queries: List[SubQuery]              # Query Planner가 이번 루프에 뽑아낸 하위 질문 리스트
    # extracted_facts: List[str]          # DB 결과를 압축해서 누적 보관할 핵심 사실 Ledger (바구니)
    loop_count: int                     # 무한 루프 방지용 카운터


class GraphAgent:
    def __init__(self):
        self.llm = LLMManager()
        self.retriever = KnowledgeRetriever()
        self.formatter = GraphFormatter()
        self.app = self._build_graph()

        self.base_path = '../../services/module-c/neo4j_label_dictionaries'
        self.label_file_map = {
            "companies": "company_dictionary.json",
            "industries": "industry_dictionary.json",
            "affiliate_groups": "affiliate_group_dictionary.json",
            "products_services": "product_service_dictionary.json"
        }

        # 2. 하드코딩 정규화 맵
        self.strict_normalization_map = {
            "삼성": "삼성전자",
            "삼전": "삼성전자",
            "삼성전자": "삼성전자",
            "SK하이닉스": "SK하이닉스",
            "현대차": "현대차",
            "현대자동차": "현대차",
            "SK스퀘어": "SK스퀘어",
            "LG엔솔": "LG에너지솔루션",
            "LG에너지솔루션": "LG에너지솔루션",
            "두산에너빌리티": "두산에너빌리티",
            "한화에어로": "한화에어로스페이스",
            "한화에어로스페이스": "한화에어로스페이스",
            "HD현대중공업": "HD현대중공업",
            "삼성바이오": "삼성바이오로직스",
            "삼성바이오로직스": "삼성바이오로직스",
            "삼성전기": "삼성전기"
        }

        # 🌟 3. [핵심] 서버 시작 시 딱 한 번만 사전을 메모리에 압축 문자열로 로드
        self.cached_dictionaries = self._init_cached_dictionaries()
    

    def _init_cached_dictionaries(self) -> dict[str, str]:
        """서버 시작 시 모든 사전 JSON을 공백 없는 문자열로 변환하여 메모리에 캐싱합니다."""
        cached = {}
        print("💾 [시스템] 상장사 및 엔티티 표준 사전 메모리 캐싱 시작...")
        
        for field_name, file_name in self.label_file_map.items():
            file_path = f"{self.base_path}/{file_name}"
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 공백과 줄바꿈을 싹 제거하여 콤팩트한 문자열 상태로 캐싱
                cached[field_name] = json.dumps(data, ensure_ascii=False)
                print(f"✅ [{field_name}] 캐싱 완료 ({len(data)}개 항목)")
            else:
                cached[field_name] = "[]"
                print(f"⚠️ [{field_name}] 사전 파일 없음. 빈 배열로 세팅.")
                
        return cached
    

    # 그래프 구성
    def _build_graph(self):
        workflow = StateGraph(GraphState)

        workflow.add_node("rewrite_query", self.rewrite_query)
        workflow.add_node("extract_entity", self.extract_entity)            # 엔티티 추출
        workflow.add_node("normalize_entities", self.normalize_entities)            # 엔티티 정규화
        workflow.add_node("plan_queries", self.plan_queries)                # 하위 쿼리 생성
        workflow.add_node("search_only_vector_db", self.search_only_vector_db) # 🆕 1차 루프용 가벼운 벡터 전용 노드
        
        
        workflow.add_node("generate_cypher", self.generate_cypher)         # 기존 사이퍼 생성
        workflow.add_node("search_databases", self.search_databases)       # 기존 ★벡터+그래프 병렬 탐색 노드★
        workflow.add_node("format_graph", self.format_graph)               # 기존 시각화 포맷팅
        workflow.add_node("generate_answer", self.generate_answer)         # 기존 최종 답변 생성

        # 2. 진입점 설정
        workflow.set_entry_point("rewrite_query")

        # 3. 직선 엣지 연결 (무조건 거치는 흐름들)
        workflow.add_edge("rewrite_query", "extract_entity")
        workflow.add_edge("normalize_entities", "plan_queries")
        workflow.add_edge("generate_cypher", "search_databases")
        # workflow.add_edge("search_databases", "extract_and_condense_facts") # 2차 병렬 탐색 종료 후 압축 노드로
        workflow.add_edge("search_only_vector_db", "plan_queries") # 1차 벡터 탐색 종료 후 압축 노드로
        
        workflow.add_edge("format_graph", "generate_answer")
        workflow.add_edge("generate_answer", END)

        # ==================================================
        # 4. 조건 분기 (Conditional Edges)
        # ==================================================

        # 분기 1: 기존 엔티티 추출 성공 여부 체크 (기존 로직 유지)
        workflow.add_conditional_edges(
            "extract_entity",
            self.check_entity_extraction_success,
            {
                "error": "generate_answer",    # 에러 시 최종 답변으로
                "success": "normalize_entities"   # 성공 시 진행
            }
        )

        # 분기 2: 몇 번째 회차냐에 따라 1차(벡터 전용)와 2차(제안서 스펙 병렬 탐색) 라인으로 분기
        workflow.add_conditional_edges(
            "plan_queries",
            self.route_by_turn,
            {
                "1st_turn_only_vector": "search_only_vector_db",
                "2nd_turn_parallel": "generate_cypher"
            }
        )

        # # 분기 3: 루프를 더 돌지, 아니면 다 모였으니 최종 시각화/답변으로 갈지 결정
        # workflow.add_conditional_edges(
        #     "extract_and_condense_facts",
        #     self.check_loop_status,
        #     {
        #         "continue_loop": "plan_queries",
        #         "go_to_format_and_end": "format_graph"
        #     }
        # )

        # 분기 3
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
            how=result.get("how"),
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
        raw_entities = result.named_entities or EntityExtractionData()

        # 🌟 [핵심 로직] 하드코딩 매칭 분리 작업
        remaining_companies = []
        pre_normalized_companies = []

        for company in getattr(raw_entities, "companies", []):
            company_clean = company.strip()
            # 하드코딩 맵에 존재하면 정규화된 이름으로 임시 방에 보관
            if company_clean in self.strict_normalization_map:
                matched_target = self.strict_normalization_map[company_clean]
                pre_normalized_companies.append(matched_target)
                print(f"⚡ [하드코딩 선점 완료] {company_clean} ➔ {matched_target} (2단계 LLM 제외)")
            else:
                # 맵에 없으면 2단계 LLM 사전을 타야 하므로 남겨둠
                remaining_companies.append(company_clean)

        # 남은 기업들로 객체 교체
        raw_entities.companies = remaining_companies
        
        return {
            "entities": raw_entities,
            "pre_normalized_companies": pre_normalized_companies, # 🌟 2단계 노드로 토스
            "error_msg": None
        }
    

    def normalize_entities(self, state: GraphState):
        user_query = state.get("query")
        raw_entities = state.get("entities") # 1단계 노드 결과 객체 (EntityExtractionData)
        pre_normalized_companies = state.get("pre_normalized_companies") or []
        
        # 🌟 핵심 기믹: 엔티티가 존재하는 카테고리의 사전만 동적으로 빌드
        dynamic_dicts_list = []
        
        # 🌟 이제 루프를 돌 때 디스크 I/O가 아니라 '메모리 읽기'만 수행합니다.
        for field_name in self.label_file_map.keys():
            extracted_list = getattr(raw_entities, field_name, [])
            
            # 1단계에서 데이터가 뽑힌 카테고리만 메모리에서 꺼내서 조립
            if extracted_list and len(extracted_list) > 0:
                compact_json_str = self.cached_dictionaries.get(field_name, "[]")
                dynamic_dicts_list.append(f"- {field_name} 사전: {compact_json_str}")
        
        if dynamic_dicts_list:
            dynamic_dictionaries_str = "\n".join(dynamic_dicts_list)
        else:
            dynamic_dictionaries_str = "(요청된 엔티티 카테고리에 해당하는 표준 사전이 존재하지 않거나 필요하지 않습니다.)"

        extracted_entities_data = raw_entities.model_dump_json(ensure_ascii=False)

        # 2단계 정규화 LLM 호출
        normalized_entities = self.llm.normalize_entities(user_query, dynamic_dictionaries_str, extracted_entities_data)
        
        # 하드코딩 결과와 LLM 정규화 결과 병합
        final_companies = list(set(normalized_entities.companies + pre_normalized_companies))
        
        # State 업데이트 데이터 조립
        final_entities = raw_entities
        final_entities.companies = final_companies
        final_entities.industries = normalized_entities.industries
        final_entities.affiliate_groups = normalized_entities.affiliate_groups
        final_entities.products_services = normalized_entities.products_services
        final_entities.people = normalized_entities.people
        
        print("🔥 [동적 사전 정규화 완료]")
        print(f"- 사용된 사전 항목: {[k for k, v in self.label_file_map.items() if getattr(raw_entities, k, [])]}")
        print(f"- 최종 정제 결과: {normalized_entities.model_dump(exclude_none=True)}")

        print(f"정규화된 엔티티 객체: {final_entities}\n")
        
        return {
            "entities": final_entities,
            "pre_normalized_companies": []
        }
    

    def _load_compact_json(self, file_name: str) -> str:
        file_path = f"{self.base_path}/{file_name}"
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return json.dumps(data, ensure_ascii=False)
        return "[]"
    

    # # 엔티티를 실제 Neo4j에 있는 엔티티로 정규화 매핑
    # def link_entity(self, entities: EntityExtractionData) -> EntityExtractionData:
    #     """
    #     Pydantic 엔티티 추출 데이터를 받아 5개 라벨에 대해 정규화를 자동 수행합니다.
    #     """
    #     # [Pydantic 필드명 : Neo4j 라벨명] 맵핑 테이블 정의
    #     label_map = {
    #         "companies": "company",
    #         "people": "person",
    #         "industries": "industry",
    #         "business_areas": "business_area",
    #         "products_services": "product_service"
    #     }

    #     # 최종 결과를 담을 응답 딕셔너리 구조 초기화
    #     refined_result = {field: [] for field in label_map.keys()}

    #     # 매핑 정보를 저장할 딕셔너리 생성
    #     name_map = {}

    #     # 5번 복사하는 대신, 단 하나의 루프로 일괄 처리
    #     for field_name, entity_type in label_map.items():
    #         # 예: getattr(entities, "companies") -> entities.companies 리스트를 가져옴
    #         original_list = getattr(entities, field_name, [])
            
    #         for original_name in original_list:
    #             matched_name = self.retriever.find_best_match(original_name, entity_type)
                
    #             if matched_name:
    #                 refined_result[field_name].append(matched_name)
    #                 name_map[original_name] = matched_name  # 추후 Cypher 변환용 매핑 기록
                    
    #                 print(f"{field_name} - 원본: {original_name} -> 매칭: {matched_name}\n")
                        
    #     # 딕셔너리를 언패킹하여 EntityExtractionData Pydantic 객체로 변환하여 리턴
    #     return EntityExtractionData(**refined_result)
    

    # 하위 질문 생성(플랜)
    def plan_queries(self, state: GraphState):
        """
        맥락 복원 및 단문 분해를 수행하는 통합 플래너 노드
        """
        user_query = state.get("query")
        extracted_company_names = state.get("entities").companies
        vector_context = state.get("vector_context", "")
        current_loop = state.get("loop_count", 0)
        
        result = self.llm.generate_sub_queries(user_query, extracted_company_names, vector_context)
        sub_queries = result.sub_queries
        # 필터링 조건을 제외하고 오직 '순수 하위 질문 문자열'만 리스트로 추출
        pure_sub_queries: List[str] = [plan.query for plan in sub_queries]
        
        # try:
        #     sub_queries = json.loads(result.strip())
        #     if not isinstance(sub_queries, list):
        #         sub_queries = [result.strip()]
        # except Exception:
        #     sub_queries = [user_query]

        print(f"\n====== [{current_loop + 1}회차 루프 플래닝 완료] ======")
        print(f"하위 질문 목록: {pure_sub_queries}\n")
        
        return {
            "sub_queries": sub_queries,
            "loop_count": current_loop + 1
        }
    

    # 벡터 DB만 탐색
    def search_only_vector_db(self, state: GraphState):
        """
        1차 루프: SubQuery 구조체 객체들을 순회하며 각각 벡터 DB를 필터와 함께 조회하고,
        [서브 쿼리 -> 탐색 결과] 구조로 예쁘게 정렬하여 반환합니다.
        """
        # 전처리 노드가 가공해서 넘겨준 SubQuery 객체 리스트 수신
        sub_queries: List[SubQuery] = state.get("sub_queries", [])
        mapped_vector_results = []
        
        print("[1차 루프: 서브 쿼리 및 메타 필터 기반 벡터 DB 순차 검색 시작]")
        
        for idx, plan in enumerate(sub_queries):
            sub_q = plan.query
            sub_filter = plan.filter  # SearchFilter 객체 혹은 None
            
            print(f" 🔍 서브 쿼리 {idx+1}/{len(sub_queries)} 검색 중: {sub_q}")
            if sub_filter:
                print(f"   └ 매핑된 필터: {sub_filter.dict()}")
            
            # 🌟 핵심 수정: 쿼리와 필터를 함께 전달
            raw_vector_result = self.retriever.chroma.search_vector_db(
                query=sub_q, 
                search_filter=sub_filter
            ) 
            
            # 구조화하여 리스트에 저장
            mapped_vector_results.append(
                f"■ 하위 질문 {idx+1}: {sub_q}\n"
                f"└ 벡터 DB 탐색 결과:\n{raw_vector_result}"
            )
        
        # 든든하게 합치기
        if not mapped_vector_results:
            final_vector_context = "조회된 벡터 DB 데이터 없음"
        else:
            final_vector_context = "\n\n=========================================\n\n".join(mapped_vector_results)
        
        print("\n[1회차 탐색 결과]\n")
        print(final_vector_context)
        print('\n')
        return {
            "vector_context": final_vector_context
        }


    # 사이퍼 쿼리 생성
    def generate_cypher(self, state: GraphState):
        user_query = state.get("query")
        entities = state.get("entities")
        sub_queries = state.get("sub_queries", [])

        # 필터링 조건을 제외하고 오직 '순수 하위 질문 문자열'만 리스트로 추출
        pure_sub_queries: List[str] = [plan.query for plan in sub_queries]

        result = self.llm.generate_cypher(user_query, pure_sub_queries, entities)

        print("[사이퍼 쿼리 생성 완료]")
        print(f"사이퍼 쿼리 생성 결과: {result}\n")

        return {
            "cypher_generation_result": result
        }


    def search_databases(self, state: GraphState):
        """
        2차 루프 (제안서 스펙 병렬 탐색): 
        Pydantic 인덱스 매핑 구조를 활용하여 하위 질문별 정밀 필터와 Cypher 쿼리를 실행합니다.
        """
        # 🌟 1. 1차 탐색 때 이미 쌓여있던 기존 벡터 컨텍스트 원문을 가져옵니다.
        existing_vector_context = state.get("vector_context", "") or ""
        if existing_vector_context == "조회된 벡터 DB 데이터 없음":
            existing_vector_context = ""

        # 🌟 2. 하위 쿼리와 필터 객체가 함께 담긴 sub_queries를 기준으로 잡습니다.
        sub_queries: List[SubQuery] = state.get("sub_queries", [])
        cypher_generation_result = state.get("cypher_generation_result")

        print("[2차 루프: 인덱스 매핑 기반 벡터(필터링) + Cypher 일괄 병렬 탐색 시작]\n")
        
        bulk_cypher_groups = cypher_generation_result.cypher_queries

        # 2차 탐색 결과를 새로 담을 리스트 (기존 1차 텍스트가 있다면 미리 얹어둡니다)
        combined_vector_chunks = []
        if existing_vector_context.strip():
            combined_vector_chunks.append(existing_vector_context)

        combined_graph_chunks = []
        all_graph_structured_data = []
        final_center_id = None 

        center_entity_name = cypher_generation_result.center_entity_name

        # 🌟 3. 루프 대상을 sub_queries 대신 sub_queries로 변경
        for idx, (plan, cypher_group) in enumerate(zip(sub_queries, bulk_cypher_groups)):
            sub_q = plan.query
            sub_filter = plan.filter  # 2차 탐색용 정밀 벡터 필터 객체
            
            current_queries = cypher_group.sub_cypher_queries if cypher_group else []
            search_query = sub_q

            print(f" 🚀 하위 질문 {idx+1} 실행 (벡터 필터 검색 1회 + 그래프 쿼리 {len(current_queries)}개 일괄 전달)")
            if sub_filter:
                print(f"   └ 2차 벡터 필터: {sub_filter.model_dump_json(indent=2)}")
            
            # 🌟 4. 수정한 대로 filter를 파라미터에 얹어서 호출
            result = self.retriever.get_corporate_context(
                query=search_query, 
                cypher_queries=current_queries, 
                center_entity_name=center_entity_name,
                search_filter=sub_filter
            )
            
            # 구조화 데이터 및 center_id 갱신
            if result.graph_db_response.graph_structured_data:
                all_graph_structured_data.extend(result.graph_db_response.graph_structured_data)
            if result.graph_db_response.center_id:
                final_center_id = result.graph_db_response.center_id
            
            graph_res_text = result.graph_db_response.graph_context if result.graph_db_response.graph_context else "조회된 그래프 데이터 없음"
            vector_res_text = result.vector_context if result.vector_context else "조회된 벡터 데이터 없음"

            # 각 하위 질문의 순서 맥락을 유지하여 누적
            combined_vector_chunks.append(
                f"■ [2차] 하위 질문 {idx+1}: {sub_q}\n└ 추출된 문서 핵심 사실:\n{vector_res_text}"
            )
            combined_graph_chunks.append(
                f"■ [2차] 하위 질문 {idx+1}: {sub_q}\n└ 추출된 지식 그래프 팩트:\n{graph_res_text}"
            )

        # 🌟 5. 대구분선으로 최종 병합 (final_vector_context에는 1차 정보와 2차 정보가 모두 포함됨)
        final_vector_context = "\n\n=========================================\n\n".join(combined_vector_chunks)
        final_graph_context = "\n\n=========================================\n\n".join(combined_graph_chunks)

        print("✅ 2차 병렬 탐색 완료 및 1차+2차 벡터 컨텍스트 최종 누적 완료.\n")

        print("\n[2회차 탐색 결과]\n")
        print(final_vector_context)
        print('\n')
        print(final_graph_context)
        print('\n')

        return {
            "vector_context": final_vector_context,  # 1차 + 2차 데이터가 통합된 최종 본문
            "graph_context": final_graph_context,
            "graph_structured_data": all_graph_structured_data,
            "center_id": final_center_id,
            "error_msg": ""
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
        recent_history_str = state.get("recent_history_str")

        # 에러가 없으면 정상적으로 LLM 호출
        final_response = self.llm.generate_final_response(
            query=user_query,
            vector_context=vector_context,
            graph_context=graph_context,
            history_context=recent_history_str
        )
        
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
    

    # def check_loop_status(self, state: GraphState):
    #     sub_queries = state.get("sub_queries", [])
    #     loop_count = state.get("loop_count", 0)
        
    #     # 2회차 루프(제안서용 병렬 탐색)가 끝났거나, 플래너가 빈 배열을 주면 종료
    #     if len(sub_queries) == 0 or loop_count >= 2:
    #         print("➔ [탐색 종료] 모든 데이터 수집 및 정제가 완료되었습니다. 시각화 및 최종 답변 생성 단계로 전진합니다.\n")
    #         return "go_to_format_and_end"
    #     else:
    #         print("➔ [루프 지속] 추가 심층 단서 수집을 위해 2회차 '벡터+그래프 병렬 탐색' 라인으로 진입합니다.\n")
    #         return "continue_loop"