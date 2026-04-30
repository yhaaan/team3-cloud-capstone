from app.config import Config
from langchain_neo4j import Neo4jGraph
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

# Neo4j(그래프 DB) 핸들러
class Neo4jHandler():
    def __init__(self):
        self.graph_db = self.get_graph_db() # 그래프 DB 초기화


    # 그래프 DB 초기화 함수
    def get_graph_db(self):
        return Neo4jGraph(
            url="bolt://localhost:7687",
            username="neo4j",
            password=Config.NEO4J_PASSWORD
        )


    # 그래프 DB 탐색 함수
    def search_graph_db(self, cypher_query: str):
        try:
            records = self.graph_db.query(cypher_query)
            raw_data = []
            for r in records:
                d = r.data()
                # LLM이 쿼리에서 RETURN n, r, m 이라고 했다고 가정할 때
                # 각 객체에 실제 DB ID를 강제로 주입 (프론트엔드 시각화용)
                if 'n' in r: d['n']['id'] = r['n'].element_id
                if 'm' in r: d['m']['id'] = r['m'].element_id
                if 'r' in r:
                    d['r']['start_id'] = r['r'].start_node.element_id
                    d['r']['end_id'] = r['r'].end_node.element_id
                    d['r']['type'] = r['r'].type
                raw_data.append(d)
            return raw_data
        except Exception as e:
            print(f"DB 실행 에러: {e}")
            return "None"
    

# 벡터 DB 핸들러
class VectorHandler():
    def __init__(self):
        self.vector_db = self.get_vector_db() # 벡터 DB 초기화


    # 벡터 DB 초기화 함수
    def get_vector_db(self):
        persist_dir = "./chroma_db"
        return Chroma(
            persist_directory=persist_dir,
            embedding_function=OpenAIEmbeddings() # 별도 인자 없을 시 환경변수의 OPENAI_API_KEY 자동 사용
        )
    

    # 벡터 DB 탐색 함수
    def search_vector_db(self, query: str):
        # 질문 전체(Full Text)를 벡터로 변환하여 유사 문서 검색
        docs = self.vector_db.similarity_search(query, k=3)
        # 가공 과정 (Document 객체에서 텍스트만 추출)
        context = "\n".join([d.page_content for d in docs])
        return context