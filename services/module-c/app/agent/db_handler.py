from typing import List, Union
from neo4j import Record
from app.config import Config
from langchain_neo4j import Neo4jGraph
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
import chromadb
from app.schemas import GraphDBSearchResponse, CypherGenerationResponse


# Neo4j(그래프 DB) 핸들러
class Neo4jHandler():
    def __init__(self):
        self.graph_db_error = None
        self.graph_db = self.get_graph_db() # 그래프 DB 초기화


    # 그래프 DB 초기화 함수
    def get_graph_db(self):
        try:
            graph = Neo4jGraph(
                url=Config.NEO4J_URI,
                username=Config.NEO4J_USER,
                password=Config.NEO4J_PASSWORD,
                database=Config.NEO4J_USER  # username 변수를 그대로 데이터베이스 이름으로 사용
            )
            # 실제 쿼리를 하나 날려보아 연결을 확인합니다.
            graph.query("RETURN 1") 
            self.graph_db_error = None
            print("✔️ 그래프 DB가 성공적으로 연결되었습니다.\n")
            return graph
        except Exception as e:
            self.graph_db_error = "❌ Neo4j 데이터베이스 연결에 실패했습니다.\n"
            # 서버 로그에는 자세히 찍음 (디버깅용)
            print(f"[CRITICAL] Neo4j Connection Failed: {e}\n")
            return None


    # 그래프 DB 탐색 함수
    def search_graph_db(self, cypher_queries: List[str], center_entity_name: str):
        try:
            # 1. 단일 문자열 쿼리가 들어온 경우 리스트로 변환하여 처리 로직 통일
            if isinstance(cypher_queries, str):
                cypher_queries = [cypher_queries]

            all_records = []

            with self.graph_db._driver.session() as session:
                # 2. 리스트에 담긴 쿼리를 하나씩 순회하며 실행
                for query in cypher_queries:
                    # 빈 문자열 등 유효하지 않은 쿼리는 스킵
                    if not query or not query.strip():
                        continue
                    
                    result = session.run(query)
                    # session.run()의 결과(Result 객체)를 list로 변환하여 전체 레코드 누적
                    all_records.extend(list(result))
                
                # 3. 누적된 모든 Record 객체들을 한 번에 처리
                graph_data = self.process_data_for_all(all_records, center_entity_name)
                
                print(graph_data)
                self.graph_db_error = None
                print(f"✔️ {len(cypher_queries)}개의 사이퍼 쿼리를 이용한 그래프 DB 탐색이 성공적으로 완료되었습니다.\n")
                return graph_data
                
        except Exception as e:
            self.graph_db_error = "❌ Neo4j 데이터베이스 탐색에 실패했습니다."
            print(f"그래프 DB 탐색 에러: {e}\n")
            return GraphDBSearchResponse(
                center_id="",
                graph_context="",
                graph_structured_data=[]
            )
        

    def process_data_for_all(self, result: List['Record'], center_name: str = ""):
        all_processed_data = [] 
        detected_center_id = ""
        
        raw_single_rels = {} 
        raw_multi_paths = {} 

        # [Pass 1] 데이터 분류 (기존과 동일)
        for record in result:
            d = record.data()
            structured_rels = []

            # 공통 노드 처리 (기존 로직 유지)
            if 'n' in record.keys() and hasattr(record['n'], 'element_id'): 
                d['n']['id'] = record['n'].element_id
                if center_name != "" and record['n'].get('name') == center_name:
                    detected_center_id = record['n'].element_id
            if 'm' in record.keys() and hasattr(record['m'], 'element_id'): 
                d['m']['id'] = record['m'].element_id
                if center_name != "" and record['m'].get('name') == center_name:
                    detected_center_id = record['m'].element_id

            # CASE A: Path (p)가 들어온 경우
            if 'p' in record.keys():
                path_obj = record['p']
                nodes_in_path = []
                for node in path_obj.nodes:
                    if center_name != "" and node.get('name') == center_name:
                        detected_center_id = node.element_id
                    nodes_in_path.append({
                        "id": node.element_id, 
                        "name": node.get('name', 'Unknown'),
                        "type": list(node.labels)[0] if node.labels else 'Entity',
                    })
                d['p'] = nodes_in_path 

                for rel in path_obj.relationships:
                    structured_rels.append(self._parse_single_rel(rel))

                if len(path_obj.nodes) > 0:
                    node_names = [node.get('name', 'Unknown') for node in path_obj.nodes]
    
                    # 수정: 순환 고리를 허용하기 위해 단순 중복 체크 제거
                    # 대신 경로가 실제로 유효한지만 체크
                    if not node_names: 
                        continue

                    path_str = f"({path_obj.nodes[0].get('name', 'Unknown')})"
                    for i, rel in enumerate(path_obj.relationships):
                        next_node = path_obj.nodes[i+1]
                        if rel.start_node.element_id == path_obj.nodes[i].element_id:
                            path_str += f" -[{rel.type}]-> ({next_node.get('name', 'Unknown')})"
                        else:
                            path_str += f" <-[{rel.type}]- ({next_node.get('name', 'Unknown')})"

                    arrow_count = path_str.count("->") + path_str.count("<-")

                    # 일단 순서 상관없이 날 데이터 그대로 분류 저장
                    if arrow_count == 1:
                        if path_str not in raw_single_rels:
                            raw_single_rels[path_str] = []
                        for rel in path_obj.relationships:
                            raw_single_rels[path_str].append(self._extract_rel_meta(rel))
                    else:
                        # [중요] 연쇄 경로는 중복 여부와 상관없이 무조건 저장
                        if path_str not in raw_multi_paths:
                            raw_multi_paths[path_str] = list(path_obj.relationships)

            # CASE B: 단일 Relationship (r)이 들어온 경우
            elif 'r' in record.keys():
                rel_obj = record['r']
                if hasattr(rel_obj, 'element_id'):
                    s_node = rel_obj.start_node
                    e_node = rel_obj.end_node
                    
                    d['n'] = {"id": s_node.element_id, "name": s_node.get('name', 'Unknown'), "type": list(s_node.labels)[0] if s_node.labels else 'Entity'}
                    d['m'] = {"id": e_node.element_id, "name": e_node.get('name', 'Unknown'), "type": list(e_node.labels)[0] if e_node.labels else 'Entity'}

                    if center_name != "" and s_node.get('name') == center_name:
                        detected_center_id = s_node.element_id
                    elif center_name != "" and e_node.get('name') == center_name:
                        detected_center_id = e_node.element_id

                    structured_rels.append(self._parse_single_rel(rel_obj))
                    
                    path_str = f"({s_node.get('name', 'Unknown')}) -[{rel_obj.type}]-> ({e_node.get('name', 'Unknown')})"
                    if path_str not in raw_single_rels:
                        raw_single_rels[path_str] = []
                    raw_single_rels[path_str].append(self._extract_rel_meta(rel_obj))

            d['r'] = structured_rels
            all_processed_data.append(d)

        # [Pass 2] 컨텍스트 조립 (우선순위 변경)
        final_context_blocks = []
        global_exposed_contents = set() # 이미 출력된 증거(evidence) 본문을 저장

        # Step 2-1. [연쇄 경로] 먼저 처리
        for path_str, rel_list in raw_multi_paths.items():
            formatted_evidences = []
            for rel in rel_list:
                evidence = rel.get('evidence', '없음')
                
                # 이미 노출된 증거라면 텍스트는 생략하고 관계선만 표시
                if evidence in global_exposed_contents:
                    s_name = rel.start_node.get('name') or "알 수 없음"
                    e_name = rel.end_node.get('name') or "알 수 없음"
                    formatted_evidences.append(f"  * [{s_name}] -({rel.type})-> [{e_name}]\n    - (상기 중복 증거 생략)")
                    continue

                # 처음 나오는 증거라면 캐싱하고 상세 내용 작성
                global_exposed_contents.add(evidence)
                s_name = rel.start_node.get('name') or "알 수 없음"
                e_name = rel.end_node.get('name') or "알 수 없음"
                
                formatted_evidences.append(
                    f"  * [{s_name}] -({rel.type})-> [{e_name}]\n"
                    f"    - 내용: {evidence}\n"
                    f"    - 발행일: {rel.get('evidence_published_at', '알 수 없음')}\n"
                    f"    - 출처/문서명: {rel.get('evidence_source_type', '알 수 없음')}\n"
                    f"    - 원문 링크: {rel.get('evidence_source_url', '알 수 없음')}"
                )
            
            if formatted_evidences:
                block = f"[연쇄 경로]\n{path_str}\n[경로 근거 자료]\n" + "\n".join(formatted_evidences)
                final_context_blocks.append(block)

        # Step 2-2. [단일 관계] 나중에 처리
        for path_str, meta_set in raw_single_rels.items():
            meta_list = sorted(list(set(meta_set)), key=lambda x: x[1])
            formatted_evidences = []
            
            for idx, meta in enumerate(meta_list, 1):
                evidence, published_at, source_type, url = meta
                
                # [핵심] 연쇄 경로에서 이미 나온 증거라면 아예 블록에서 제외하거나 생략 메시지 출력
                if evidence in global_exposed_contents:
                    # 단일 관계의 경우, 이미 위에서 자세히 설명됐다면 굳이 또 보여줄 필요가 없음
                    # (또는 간단히 '상기 연쇄 경로 참조'라고 적을 수 있음)
                    continue 

                global_exposed_contents.add(evidence)
                formatted_evidences.append(
                    f"  * 근거 {len(formatted_evidences)+1}\n"
                    f"    - 내용: {evidence}\n"
                    f"    - 발행일: {published_at}\n"
                    f"    - 출처/문서명: {source_type}\n"
                    f"    - 원문 링크: {url}"
                )
                
            if formatted_evidences:
                block = f"[단일 관계]\n{path_str}\n[경로 근거 자료]\n" + "\n".join(formatted_evidences)
                final_context_blocks.append(block)

        final_context = "\n\n".join(final_context_blocks) if final_context_blocks else ""

        return GraphDBSearchResponse(
            center_id=detected_center_id,
            graph_context=final_context,
            graph_structured_data=all_processed_data
        )


    def _extract_rel_meta(self, rel_obj) -> tuple:
        """딕셔너리 저장을 위해 메타데이터를 정제된 튜플로 반환하는 헬퍼 함수"""
        return (
            rel_obj.get('evidence', '없음'),
            rel_obj.get('evidence_published_at', '알 수 없음'),
            rel_obj.get('evidence_source_type', '알 수 없음'),
            rel_obj.get('evidence_source_url', '알 수 없음')
        )
    

    def _parse_single_rel(self, rel_obj):
        """Relationship 객체 하나를 받아서 프론트용 dict로 변환"""
        return {
            "id": rel_obj.element_id,
            "type": rel_obj.type,
            "start_id": rel_obj.start_node.element_id,
            "end_id": rel_obj.end_node.element_id,
            "properties": dict(rel_obj)
        }

    # def _make_llm_context(self, rel_obj):
    #     """LLM이 읽을 문장 생성"""
    #     s_name = rel_obj.start_node.get('name') or "알 수 없음"
    #     e_name = rel_obj.end_node.get('name') or "알 수 없음"
    #     evidence = rel_obj.get('evidence', '없음')
    #     evidence_published_at = rel_obj.get('evidence_published_at', '알 수 없음')
    #     evidence_source_type = rel_obj.get('evidence_source_type', '알 수 없음')
    #     evidence_source_url = rel_obj.get('evidence_source_url', '알 수 없음')

    #     graph_text = (
    #         f"[{s_name}] -({rel_obj.type})-> [{e_name}]\n"
    #         f"근거: {evidence}\n"
    #         f"- 발행일: {evidence_published_at}\n"
    #         f"- 출처/문서명: {evidence_source_type}\n"
    #         f"- 원문 링크: {evidence_source_url}\n"
    #     )
    #     return graph_text


    # 해당 타입 모든 노드 이름 가져오기 함수
    # Neo4j 노드 type - 'Company', 'Person', 'Event', 'Industry'
    def get_node_names_by_type(self, entity_type: str):
        # 내부의 driver를 직접 사용
        try:
            with self.graph_db._driver.session() as session:
                query = "MATCH (n) WHERE n.type = $entity_type RETURN n.name AS name"
                result = session.run(query, entity_type=entity_type)
                # 데이터를 리스트로 변환
                names = [record["name"] for record in result if record["name"]]
                return names
        except Exception as e:
            self.graph_db_error = "❌ Neo4j 데이터베이스 탐색에 실패했습니다."
            print(f"그래프 DB 탐색 에러: {e}\n")
            return None
    

# 벡터 DB 핸들러
class VectorHandler():
    def __init__(self):
        self.vector_db_error = None
        self.vector_db = self.get_vector_db() # 벡터 DB 초기화
       

    # 벡터 DB 초기화 함수
    def get_vector_db(self):
        try:
            # 지정된 경로로 클라이언트 생성
            client = chromadb.PersistentClient(
                path="../module-b/local_db/chroma"
            )
            
            # 임베딩 모델 설정
            embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=Config.OPENAI_API_KEY
            )
            
            # LangChain의 Chroma 객체와 연결
            # collection_name은 "module_b_chunks"로 지정
            vector = Chroma(
                client=client,
                collection_name="module_b_chunks",
                embedding_function=embeddings
            )

            # heartbeat 대신 '더미 검색'으로 실제 작동 여부 확인
            # 아주 짧은 텍스트로 1개의 결과만 찾아보게 시도
            vector.similarity_search("health check", k=1)
            self.vector_db_error = None
            print("✔️ 벡터 DB가 성공적으로 연결되었습니다.")
            print(f"벡터 DB 데이터 개수: {vector._collection.count()}\n")
            return vector
        except Exception as e:
            self.vector_db_error = "❌ ChromaDB 데이터베이스 연결에 실패했습니다."
            # 서버 로그에는 자세히 찍음 (디버깅용)
            print(f"[CRITICAL] ChromaDB Connection Failed: {e}\n")
            # 프론트엔드에 전달하기 위해 None을 반환하거나 에러를 발생시킴
            return None
    

    def search_vector_db(self, query: str, window_size: int = 2):
        try:
            # 1. 유사한 청크 검색 (k=3)
            initial_docs = self.vector_db.similarity_search(query, k=3)
            
            formatted_contexts = []
            
            for i, d in enumerate(initial_docs):
                doc_id = d.metadata.get('doc_id')
                current_idx = d.metadata.get('chunk_index')
                
                # 맥락 확장 로직
                if doc_id and current_idx is not None:
                    # [수정 포인트] window_size만큼 인덱스 범위 생성
                    # 예: idx가 5이고 window_size가 2이면 [3, 4, 5, 6, 7] 생성
                    start_idx = max(0, current_idx - window_size)
                    end_idx = current_idx + window_size
                    context_indices = list(range(start_idx, end_idx + 1))
                    
                    # ChromaDB에서 범위 내 청크들 한 번에 가져오기
                    related_chunks = self.vector_db.get(
                        where={
                            "$and": [
                                {"doc_id": {"$eq": doc_id}},
                                {"chunk_index": {"$in": context_indices}}
                            ]
                        }
                    )
                    
                    # 가져온 청크들을 인덱스 순서대로 정렬 (중요!)
                    combined_docs = sorted(
                        zip(related_chunks['metadatas'], related_chunks['documents']),
                        key=lambda x: x[0].get('chunk_index', 0)
                    )
                    
                    # 텍스트 병합 (청크 사이를 자연스럽게 띄어줌)
                    full_text = " ".join([text for meta, text in combined_docs])
                else:
                    full_text = d.page_content

                # 2. 메타데이터 추출 및 포맷팅
                source = d.metadata.get('source', '알 수 없는 출처')
                title = d.metadata.get('title', '제목 없음')
                pub_date = d.metadata.get('published_at', '날짜 미상')
                url = d.metadata.get('url', '링크 없음')
                
                chunk_text = (
                    f"--- [문서 {i+1} 출처 정보] ---\n"
                    f"발행일: {pub_date}\n"
                    f"출처/문서명: {source} ({title})\n"
                    f"원문 링크: {url}\n"
                    f"내용: {full_text}\n"
                )
                formatted_contexts.append(chunk_text)
            
            full_context = "\n\n".join(formatted_contexts)
            print(f"✔️ Window Size {window_size}가 적용된 맥락 확장이 완료되었습니다.\n")
            return full_context

        except Exception as e:
            print(f"벡터 DB 탐색 에러: {e}")
            return None