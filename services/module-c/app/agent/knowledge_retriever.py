from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.agent.db_handler import VectorHandler, Neo4jHandler 
from sklearn.feature_extraction.text import TfidfVectorizer
from app.schemas import GraphDBSearchResponse


class DBSearchResponse(BaseModel):
    vector_context: str
    graph_db_response: GraphDBSearchResponse
    db_error_msg: Optional[str] = None # DB 에러 정보를 담을 필드 추가 (Optional)


class KnowledgeRetriever:
    def __init__(self):
        self.chroma = None
        self.neo4j = None
        self.combined_db_error_msg = None
        self.vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3))
        self.company_node_names = None
        self.person_node_names = None
        self.company_entity_matrix = None
        self.person_entity_matrix = None
        self.check_connection()
    

    # DB 연결 함수
    def connect_db(self):
        self.chroma = VectorHandler()
        self.neo4j = Neo4jHandler()
        self.db_connect_error_msg = self.get_combined_db_error()

        # Neo4j에서 노드 이름을 타입별로 가져와 학습시켜 둠(일단 회사, 사람만 함)
        self.company_node_names = self.neo4j.get_node_names_by_type("Company")
        self.person_node_names = self.neo4j.get_node_names_by_type("Person")
        self.vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3))
        self.company_entity_matrix = self.vectorizer.fit_transform(self.company_node_names)
        self.person_entity_matrix = self.vectorizer.fit_transform(self.person_node_names)


    # DB 연결 성공 여부 확인 함수
    def check_connection(self):
        # [핵심] 이미 연결되어 있고 에러가 없다면 다시 연결하지 않음!
        if self.neo4j and self.chroma and self.db_connect_error_msg is None:
            return True
            
        self.connect_db()
        if self.db_connect_error_msg:
            return False


    # DB 병렬 탐색 함수
    def get_corporate_context(self, query: str, cypher_query: str) -> DBSearchResponse:
        vector_search_result = self.chroma.search_vector_db(query)
        graph_search_result = self.neo4j.search_graph_db(cypher_query)

        return DBSearchResponse(
            vector_context=vector_search_result,
            graph_db_response = graph_search_result,
            db_error_msg = self.get_combined_db_error()
        )
    

    # DB 통합 에러 메시지 얻기 함수
    def get_combined_db_error(self):
        # 에러 메시지 통합 로직
        errors = []
        # 각 인스턴스에 저장된 에러 메시지가 있는지 확인 (문자열이 존재하면 리스트에 추가)
        if self.neo4j.graph_db_error:
            errors.append(f"Graph DB Error: {self.neo4j.graph_db_error}")
        if self.chroma.vector_db_error:
            errors.append(f"Vector DB Error: {self.chroma.vector_db_error}")

        # 리스트에 에러가 있으면 줄바꿈으로 합치고, 없으면 None 반환
        # "\n".join(errors)는 리스트 요소 사이에 \n을 넣어 하나의 문자열로 만듭니다.
        combined_error = "\n\n".join(errors) if errors else None
        return combined_error
        