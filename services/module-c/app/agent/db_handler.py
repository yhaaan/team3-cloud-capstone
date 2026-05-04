from typing import Iterable, List
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

            rel_source = record.get('r') or record.get('p')
            if rel_source is not None:
                structured_rels = []
                
                # 1. 이미 리스트거나 Path 객체(p)라면 그대로 사용
                # 2. 만약 단일 Relationship 객체(r)라면 [rel_source] 로 감싸서 리스트로 변환
                # dict와 str도 Iterable에 해당하므로, 이들은 제외하고 체크하는 것이 안전합니다.
                if isinstance(rel_source, Iterable) and not isinstance(rel_source, (str, dict)):
                    rel_list = rel_source
                else:
                    rel_list = [rel_source] # 단일 객체를 리스트에 담기
                
                for rel_obj in rel_list:
                    # (1) 관계 딕셔너리화 (start_id, end_id 주입)
                    rel_info = {
                        "id": rel_obj.element_id,
                        "type": rel_obj.type,
                        "start_id": rel_obj.start_node.element_id,
                        "end_id": rel_obj.end_node.element_id,
                        "properties": dict(rel_obj)
                    }
                    structured_rels.append(rel_info)

                    # (2) LLM용 텍스트 생성
                    s_name = rel_obj.start_node.get('name') or "알 수 없음"
                    e_name = rel_obj.end_node.get('name') or "알 수 없음"
                    llm_contexts.append(f"[{s_name}] -({rel_obj.type})-> [{e_name}]\n근거: {rel_obj.get('evidence', '없음')}")

                    # (3) ★중간 노드 추출★ 
                    # 관계의 양 끝 노드가 n이나 m이 아닐 수도 있으므로, 
                    # 프론트엔드에서 노드 리스트를 만들 때 누락되지 않게 따로 챙겨야 합니다.
                    # 여기서는 'nodes'라는 키를 d에 추가해서 모든 관련 노드 객체를 담아줍니다.
                    if 'all_nodes' not in d.keys(): 
                        d['all_nodes'] = {}
                    
                    for node in [rel_obj.start_node, rel_obj.end_node]:
                        node_id = node.element_id
                        d['all_nodes'][node_id] = {
                            "id": node_id,
                            "label": node.get('name') or "Unknown",
                            "type": list(node.labels)[0] if node.labels else "Entity",
                            "properties": dict(node)
                        }

                d['r'] = structured_rels # 수정 불가능했던 리스트를 정제된 리스트로 교체

            all_processed_data.append(d)

        unique_contexts = list(set(llm_contexts))
        final_context = "\n\n".join(unique_contexts) if unique_contexts else ""

        return GraphDBSearchResponse(
            graph_context=final_context,
            graph_structured_data=all_processed_data
        )


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
            # persist_dir = "./chroma_db"
            # vector = Chroma(
            #     persist_directory=persist_dir,
            #     embedding_function=OpenAIEmbeddings(api_key=Config.OPENAI_API_KEY)
            # )
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
    

    # 벡터 DB 탐색 함수
    def search_vector_db(self, query: str):
        try:
            # 질문 전체(Full Text)를 벡터로 변환하여 유사 문서 검색
            docs = self.vector_db.similarity_search(query, k=3)
            # 가공 과정 (Document 객체에서 텍스트만 추출)
            context = "\n".join([d.page_content for d in docs])
            self.vector_db_error = None
            print("✔️ 벡터 DB 탐색이 성공적으로 완료되었습니다.")
            return context
        except Exception as e:
            self.vector_db_error = "❌ ChromaDB 데이터베이스 탐색에 실패했습니다."
            print(f"벡터 DB 탐색 에러: {e}")
            return None