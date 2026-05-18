import json
import re
from langgraph.graph import StateGraph, END
from app.agent.llm_manager import LLMManager
from app.agent.knowledge_retriever import KnowledgeRetriever
from app.agent.graph_formatter import GraphFormatter
from typing import Any, Dict, Optional, TypedDict, List
from app.schemas import RelationGraph, EntityExtractionData, ChatResponse, CypherGenerationResponse


# 상태 정의
class GraphState(TypedDict):
    query: str                          # 사용자의 질문
    recent_history_str: str             # 최근 대화 문자열(현재 질문 제외 2쌍(4개) 메시지)
    entities: EntityExtractionData      # 질문에서 추출된 엔티티
    error_msg: str                      # 에러 메시지
    cypher_generation_result: CypherGenerationResponse # 사이퍼 쿼리 생성 결과
    vector_context: str                 # 벡터 DB 탐색 결과
    graph_context: str                  # 그래프 DB 탐색 결과(llm이 알기 쉽게 관계 하나 하나를 글 형태로 정리)
    graph_structured_data: List[Dict[str, Any]] # 그래프 DB 탐색 결과를 구조화한 데이터(시각화를 위해 노드의 id와 같은 부가 정보 전부 포함된 구조화된 데이터)
    final_response: str                 # 최종 답변
    relation_graph: RelationGraph       # 그래프 DB 탐색 결과 구조화 데이터
    how: str                            # 그래프 종류
    # has_center: Optional[bool] = False  # 구조화 데이터 중앙 노드 존재 여부
    center_id: str                    # 구조화 데이터 중앙 노드 이름

    # 🔥 [새로 추가해야 할 동적 루프용 필드]
    sub_queries: List[str]              # Query Planner가 이번 루프에 뽑아낸 하위 질문 리스트
    extracted_facts: List[str]          # DB 결과를 압축해서 누적 보관할 핵심 사실 Ledger (바구니)
    loop_count: int                     # 무한 루프 방지용 카운터


class GraphAgent:
    def __init__(self):
        self.llm = LLMManager()
        self.retriever = KnowledgeRetriever()
        self.formatter = GraphFormatter()
        self.app = self._build_graph()


    # 그래프 구성
    def _build_graph(self):
        workflow = StateGraph(GraphState)

        # 1. 노드 등록 (기존 노드 100% 재사용 + 루프용 노드 2개만 추가)
        workflow.add_node("plan_queries", self.plan_queries)               # 🆕 신규 통합 플래너
        workflow.add_node("search_only_vector_db", self.search_only_vector_db) # 🆕 1차 루프용 가벼운 벡터 전용 노드
        
        workflow.add_node("extract_entity", self.extract_entity)           # 기존 엔티티 추출
        workflow.add_node("generate_cypher", self.generate_cypher)         # 기존 사이퍼 생성
        workflow.add_node("search_databases", self.search_databases)       # 기존 ★벡터+그래프 병렬 탐색 노드★
        
        workflow.add_node("extract_and_condense_facts", self.extract_and_condense_facts) # 🆕 신규 팩트 정제/압축
        workflow.add_node("format_graph", self.format_graph)               # 기존 시각화 포맷팅
        workflow.add_node("generate_answer", self.generate_answer)         # 기존 최종 답변 생성

        # 2. 진입점 설정
        workflow.set_entry_point("plan_queries")

        # 3. 직선 엣지 연결 (무조건 거치는 흐름들)
        workflow.add_edge("extract_entity", "generate_cypher")
        workflow.add_edge("generate_cypher", "search_databases")
        workflow.add_edge("search_databases", "extract_and_condense_facts") # 2차 병렬 탐색 종료 후 압축 노드로
        workflow.add_edge("search_only_vector_db", "extract_and_condense_facts") # 1차 벡터 탐색 종료 후 압축 노드로
        
        workflow.add_edge("format_graph", "generate_answer")
        workflow.add_edge("generate_answer", END)

        # ==================================================
        # 4. 조건 분기 (Conditional Edges)
        # ==================================================
        
        # 분기 1: 몇 번째 회차냐에 따라 1차(벡터 전용)와 2차(제안서 스펙 병렬 탐색) 라인으로 분기
        workflow.add_conditional_edges(
            "plan_queries",
            self.route_by_turn,
            {
                "1st_turn_only_vector": "search_only_vector_db",
                "2nd_turn_parallel": "extract_entity"  # 엔티티 추출 -> Cypher -> search_databases(병렬탐색)로 이어짐
            }
        )

        # 분기 2: 기존 엔티티 추출 성공 여부 체크 (기존 로직 유지)
        workflow.add_conditional_edges(
            "extract_entity",
            self.check_entity_extraction_success,
            {
                "error": "generate_answer",    # 에러 시 최종 답변으로
                "success": "generate_cypher"   # 성공 시 진행
            }
        )

        # 분기 3: 루프를 더 돌지, 아니면 다 모였으니 최종 시각화/답변으로 갈지 결정
        workflow.add_conditional_edges(
            "extract_and_condense_facts",
            self.check_loop_status,
            {
                "continue_loop": "plan_queries",
                "go_to_format_and_end": "format_graph"
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
    

    def plan_queries(self, state: GraphState):
        """
        맥락 복원 및 단문 분해를 수행하는 통합 플래너 노드
        """
        user_query = state.get("query")
        recent_history_str = state.get("recent_history_str", "")
        extracted_facts = state.get("extracted_facts", [])
        current_loop = state.get("loop_count", 0)
        
        result = self.llm.generate_sub_queries(user_query, recent_history_str, extracted_facts)
        
        try:
            sub_queries = json.loads(result.strip())
            if not isinstance(sub_queries, list):
                sub_queries = [result.strip()]
        except Exception:
            sub_queries = [user_query]

        print(f"\n====== [{current_loop + 1}회차 루프 플래닝 완료] ======")
        print(f"하위 질문 목록: {sub_queries}\n")
        
        return {
            "sub_queries": sub_queries,
            "loop_count": current_loop + 1
        }
    

    def search_only_vector_db(self, state: GraphState):
        """
        1차 루프: 서브 쿼리 리스트를 순회하며 각각 벡터 DB를 조회하고,
        [서브 쿼리 -> 탐색 결과] 구조로 예쁘게 정렬하여 반환합니다.
        """
        sub_queries = state.get("sub_queries", [])
        mapped_vector_results = []
        
        print("[1차 루프: 서브 쿼리별 벡터 DB 순차 검색 시작]")
        for idx, sub_q in enumerate(sub_queries):
            print(f" 🔍 서브 쿼리 {idx+1}/{len(sub_queries)} 검색 중: {sub_q}")
            
            # 각 서브 쿼리에 대한 벡터 검색 수행
            raw_vector_result = self.retriever.chroma.search_vector_db(sub_q) 
            
            # ⚠️ 컨텍스트가 너무 길다면 여기서 일부 슬라이싱하거나 상위 k개만 제한하는 것을 권장합니다.
            # 예: raw_vector_result = raw_vector_result[:4000] 
            
            # 구조화하여 리스트에 저장
            mapped_vector_results.append(
                f"■ 하위 질문 {idx+1}: {sub_q}\n"
                f"└ 벡터 DB 탐색 결과:\n{raw_vector_result}"
            )
        
        # 서브 쿼리 1, 결과 1, 서브 쿼리 2, 결과 2... 형태로 이쁘게 조인
        final_vector_context = "\n\n=========================================\n\n".join(mapped_vector_results)
        
        return {
            "vector_context": final_vector_context
        }
    

    def extract_and_condense_facts(self, state: GraphState):
        """
        방대한 DB 탐색 결과(벡터, 그래프)를 콤팩트한 팩트로 가공하여 Ledger에 누적하는 노드
        """
        sub_queries = state.get("sub_queries", [])
        vector_context = state.get("vector_context", "")
        graph_context = state.get("graph_context", "")       # 2차 루프 시 기존 search_databases에 의해 채워짐
        existing_facts = state.get("extracted_facts", [])
        
        # 1. 두 컨텍스트를 하나로 병합
        merged_context = f"[Vector Result]\n{vector_context}"
        if graph_context.strip():
            merged_context += f"\n\n[Graph Result]\n{graph_context}"
            
        if not vector_context.strip() and not graph_context.strip():
            return {"vector_context": "", "graph_context": ""}
        
        print(merged_context)
        print('\n')
        
        result = self.llm.extract_info_from_db_context(
            sub_queries=sub_queries,
            raw_contexts=merged_context
        )
        
        try:
            new_facts = json.loads(result.strip())
            if not isinstance(new_facts, list):
                new_facts = []
        except Exception:
            new_facts = []
        
        updated_facts = existing_facts + new_facts
        print(f"[알림] {state.get('loop_count')}회차 데이터 압축 완료 및 Fact Ledger 누적.")
        print(f"-> 현재 Ledger 상태: {updated_facts}\n")
        
        print(f"[알림] 팩트 추출 완료 및 턴 종료. 현재까지 누적된 요약본 개수: {len(updated_facts)}개")
        
        return {
            "extracted_facts": updated_facts,
            "vector_context": "",
            "graph_context": ""
        }
    

    # # 질문 재구성
    # def rewrite_query(self, state: GraphState):
    #     user_query = state.get("query")
    #     recent_history_str = state.get("recent_history_str")
        
    #     result = self.llm.rewrite_query(user_query, recent_history_str)

    #     print("[질문 재구성 완료]")
    #     print(f"재구성된 질문: {result}\n")
        
    #     return {
    #         "query": result
    #     }
    

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
        sub_queries = state.get("sub_queries", [])
        result = self.llm.generate_cypher(user_query, sub_queries, entities)

        print("[사이퍼 쿼리 생성 완료]")
        print(f"사이퍼 쿼리 생성 결과: {result}\n")

        # has_center, center_id = self.extract_center_from_cypher(result)

        return {
            "cypher_generation_result": result
        }
    

    # # 사이퍼 쿼리에서 중앙 노드 추출
    # def extract_center_from_cypher(self, cypher_query):
    #     # n.name 또는 {name: ...} 패턴에서 이름들만 모두 추출
    #     patterns = [
    #         r"n\.name\s*=\s*['\"]([^'\"]+)['\"]",
    #         r"\{\s*name\s*:\s*['\"]([^'\"]+)['\"]"
    #     ]
        
    #     found_names = []
    #     for p in patterns:
    #         found_names.extend(re.findall(p, cypher_query))
        
    #     # 중복된 이름이 있을 수 있으니 집합(set)으로 유니크하게 관리
    #     unique_names = list(set(found_names))

    #     # [핵심 로직] 정확히 1개일 때만 센터로 인정
    #     if len(unique_names) == 1:
    #         return True, unique_names[0]
        
    #     # 0개이거나 2개 이상이면 무조건 False
    #     return False, None


    def search_databases(self, state: GraphState):
        """
        2차 루프 (제안서 스펙 병렬 탐색): 
        Pydantic 인덱스 매핑 구조를 활용하여 LLM 1회 호출로 모든 쿼리를 수집하고,
        하위 질문별로 N개의 Cypher 쿼리를 실행합니다.
        """
        sub_queries = state.get("sub_queries", [])
        cypher_generation_result = state.get("cypher_generation_result")

        print("[2차 루프: 인덱스 매핑 기반 Cypher 일괄 생성 및 탐색 시작]\n")
        
        # 하위 질문별 쿼리 묶음 리스트 추출
        bulk_cypher_groups = cypher_generation_result.cypher_queries

        combined_vector_chunks = []
        combined_graph_chunks = []
        all_graph_structured_data = []
        final_center_id = None 

        center_entity_name = cypher_generation_result.center_entity_name

        for idx, (sub_q, cypher_group) in enumerate(zip(sub_queries, bulk_cypher_groups)):
            # 하위 질문 하나에 매핑된 '사이퍼 쿼리 리스트' 통째로 준비
            current_queries = cypher_group.sub_cypher_queries if cypher_group else []
            
            search_query = sub_q
            # if any(k in sub_q for k in ["대주주", "주주 구성", "총수", "지분"]):
            #     search_query = f"{sub_q} 최대주주 현황 및 특수관계인 지분율 명부 dart 공시"

            print(f" 🚀 하위 질문 {idx+1} 실행 (벡터 1회 + 그래프 쿼리 리스트 {len(current_queries)}개 일괄 전달)")
            
            # ⭕ retriever 호출 (단위 일괄 던지기)
            result = self.retriever.get_corporate_context(search_query, current_queries, center_entity_name)
            
            # 🚨 [수정] 중간에 중복으로 append 하던 잘못된 조건문 블록 제거 
            
            # 구조화 데이터 및 center_id 갱신
            if result.graph_db_response.graph_structured_data:
                all_graph_structured_data.extend(result.graph_db_response.graph_structured_data)
            if result.graph_db_response.center_id:
                final_center_id = result.graph_db_response.center_id
            
            # 4. 결과 조인 및 컨텍스트 누적 (여기서 한 번에 깔끔하게 처리)
            graph_res_text = result.graph_db_response.graph_context if result.graph_db_response.graph_context else "조회된 그래프 데이터 없음"
            vector_res_text = result.vector_context if result.vector_context else "조회된 벡터 데이터 없음"

            # 각 하위 질문의 순서 맥락을 유지하기 위해 이정표(라벨)를 붙여 청크에 단 1번씩만 누적
            combined_vector_chunks.append(
                f"■ 하위 질문 {idx+1}: {sub_q}\n└ 추출된 문서 핵심 사실:\n{vector_res_text}"
            )
            combined_graph_chunks.append(
                f"■ 하위 질문 {idx+1}: {sub_q}\n└ 추출된 지식 그래프 팩트:\n{graph_res_text}"
            )

        # 루프가 완전히 끝난 뒤 (For문 밖)
        # 각 하위 질문별로 파편화되어 쌓인 팩트 덩어리들을 대구분선으로 병합
        final_vector_context = "\n\n=========================================\n\n".join(combined_vector_chunks)
        final_graph_context = "\n\n=========================================\n\n".join(combined_graph_chunks)

        print("✅ 하위 질문 리스트 단위의 일괄 벡터/그래프 탐색 및 팩트 추출이 완료되었습니다.\n")

        return {
            "vector_context": final_vector_context,
            "graph_context": final_graph_context,
            "graph_structured_data": all_graph_structured_data,
            "center_id": final_center_id,
            "error_msg": ""
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
    

    def route_by_turn(self, state: GraphState):
        loop_count = state.get("loop_count", 0)
        if loop_count == 1:
            return "1st_turn_only_vector"
        else:
            return "2nd_turn_parallel"


    def check_loop_status(self, state: GraphState):
        sub_queries = state.get("sub_queries", [])
        loop_count = state.get("loop_count", 0)
        
        # 2회차 루프(제안서용 병렬 탐색)가 끝났거나, 플래너가 빈 배열을 주면 종료
        if len(sub_queries) == 0 or loop_count >= 2:
            print("➔ [탐색 종료] 모든 데이터 수집 및 정제가 완료되었습니다. 시각화 및 최종 답변 생성 단계로 전진합니다.\n")
            return "go_to_format_and_end"
        else:
            print("➔ [루프 지속] 추가 심층 단서 수집을 위해 2회차 '벡터+그래프 병렬 탐색' 라인으로 진입합니다.\n")
            return "continue_loop"