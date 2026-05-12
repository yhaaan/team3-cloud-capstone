from typing import List
from neo4j import Record
from app.config import Config
from langchain_neo4j import Neo4jGraph
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
import chromadb
from app.schemas import GraphDBSearchResponse


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
            print("✔️ 그래프 DB가 성공적으로 연결되었습니다.")
            return graph
        except Exception as e:
            self.graph_db_error = "❌ Neo4j 데이터베이스 연결에 실패했습니다."
            # 서버 로그에는 자세히 찍음 (디버깅용)
            print(f"[CRITICAL] Neo4j Connection Failed: {e}")
            return None


    # 그래프 DB 탐색 함수
    def search_graph_db(self, cypher_query: str):
        try:
            # self.graph_db가 LangChain 객체라면 보통 내부에 드라이버가 있습니다.
            # 드라이버를 직접 써서 세션을 열면 Record 객체가 옵니다.
            with self.graph_db._driver.session() as session:
                result = session.run(cypher_query)
                graph_data = self.process_data_for_all(result)
                print(graph_data)
                self.graph_db_error = None
                print("✔️ 그래프 DB 탐색이 성공적으로 완료되었습니다.")
                return graph_data
        except Exception as e:
            self.graph_db_error = "❌ Neo4j 데이터베이스 탐색에 실패했습니다."
            print(f"그래프 DB 탐색 에러: {e}")
            return GraphDBSearchResponse(
                graph_context="",
                graph_structured_data=[]
            )
        

    def process_data_for_all(self, result: List[Record]):
        all_processed_data = [] # 최종 결과물 리스트
        llm_contexts = []

        for record in result:
            print(record, '\n')
            # r.data()는 기본 틀만 가져오고, 실제 ID 노가다는 r(Record)로 합니다.
            d = record.data()
            
            # 1. 양 끝 노드 처리 (기존 로직 유지)
            if 'n' in record.keys(): 
                d['n']['id'] = record['n'].element_id
            if 'm' in record.keys(): 
                d['m']['id'] = record['m'].element_id

            structured_rels = []

            # --- 로직 분리 ---
            
            # CASE A: Path (p)가 들어온 경우
            if 'p' in record.keys():
                path_obj = record['p']
                
                # --- 추가: Path 내의 모든 노드 정보를 추출하여 d['p']에 저장 ---
                nodes_in_path = []
                for node in path_obj.nodes:
                    nodes_in_path.append({
                        "id": node.element_id,
                        "name": node.get('name', 'Unknown'),
                        "type": list(node.labels)[0] if node.labels else 'Entity',
                        # 필요한 다른 속성들 추가
                    })
                d['p'] = nodes_in_path # 이제 '인공지능' 노드의 ID와 이름이 매핑되어 들어감!

                # 기존 관계 파싱 로직
                for rel in path_obj.relationships:
                    rel_info = self._parse_single_rel(rel)
                    structured_rels.append(rel_info)
                    llm_contexts.append(self._make_llm_context(rel))

            # CASE B: 단일 Relationship (r)이 들어온 경우
            elif 'r' in record.keys():
                rel_obj = record['r']
                print(f"rel_obj: {rel_obj}\n")
                rel_obj.element_id
                # r이 만약 문자열(str)로 들어오는 예외 상황 방어
                if hasattr(rel_obj, 'element_id'):
                    rel_info = self._parse_single_rel(rel_obj)
                    structured_rels.append(rel_info)
                    llm_contexts.append(self._make_llm_context(rel_obj))

            d['r'] = structured_rels
            all_processed_data.append(d)

        unique_contexts = list(set(llm_contexts))
        final_context = "\n\n".join(unique_contexts) if unique_contexts else ""

        return GraphDBSearchResponse(
            graph_context=final_context,
            graph_structured_data=all_processed_data
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

    def _make_llm_context(self, rel_obj):
        """LLM이 읽을 문장 생성"""
        s_name = rel_obj.start_node.get('name') or "알 수 없음"
        e_name = rel_obj.end_node.get('name') or "알 수 없음"
        evidence = rel_obj.get('evidence', '없음')
        return f"[{s_name}] -({rel_obj.type})-> [{e_name}]\n근거: {evidence}"


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
            print(f"그래프 DB 탐색 에러: {e}")
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
            print(f"벡터 DB 데이터 개수: {vector._collection.count()}")
            return vector
        except Exception as e:
            self.vector_db_error = "❌ ChromaDB 데이터베이스 연결에 실패했습니다."
            # 서버 로그에는 자세히 찍음 (디버깅용)
            print(f"[CRITICAL] ChromaDB Connection Failed: {e}")
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
            print(f"✔️ Window Size {window_size}가 적용된 맥락 확장이 완료되었습니다.")
            return full_context

        except Exception as e:
            print(f"벡터 DB 탐색 에러: {e}")
            return None