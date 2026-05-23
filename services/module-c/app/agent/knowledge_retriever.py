import os
from pathlib import Path
from typing import List, Optional
import numpy as np
from openai import OpenAI
from pydantic import BaseModel
from sklearn.metrics.pairwise import cosine_similarity
from app.agent.db_handler import VectorHandler, Neo4jHandler 
from app.schemas import GraphDBSearchResponse, SearchFilter
from app.config import Config
from app.utils import get_embeddings


class DBSearchResponse(BaseModel):
    vector_context: str
    graph_db_response: GraphDBSearchResponse
    db_error_msg: Optional[str] = None # DB 에러 정보를 담을 필드 추가 (Optional)


class KnowledgeRetriever:
    def __init__(self):
        self.chroma = None
        self.neo4j = None
        self.combined_db_error_msg = None

        # 이름 리스트 및 임베딩 저장용
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        # self.company_node_names = []
        # self.person_node_names = []
        # self.company_embeddings = None
        # self.person_embeddings = None

        # 라벨 리스트 정의 (Pydantic 필드명 및 Neo4j 라벨과 동기화)
        self.entity_labels = ["company", "person", "industry", "business_area", "product_service"]
        
        # 데이터를 담을 딕셔너리 초기화
        self.node_embeddings = {}
        self.node_names = {}

        self.check_connection()
    

    # DB 연결 함수
    def connect_db(self):
        # try:
        #     base_path = Path(__file__).resolve().parents[2] / "neo4j_label_embeddings"
            
        #     # print("현재 작업 디렉토리:", os.getcwd())
        #     for label in self.entity_labels:
        #         file_name_prefix = label.lower() # 파일명 소문자 대응

        #         embeddings_path = base_path / f"{file_name_prefix}_embeddings.npy"
        #         names_path = base_path / f"{file_name_prefix}_names.npy"
                
        #         # 경로와 파일명을 동적으로 생성하여 자동 로드
        #         self.node_embeddings[label] = np.load(embeddings_path)
        #         self.node_names[label] = np.load(names_path).tolist()
            
        # except FileNotFoundError as e:
        #     print(f"임베딩 파일 로드 실패: {e}")
        #     self.db_connect_error_msg = "Embedding files not found."
        #     return

        self.chroma = VectorHandler()
        self.neo4j = Neo4jHandler()
        self.db_connect_error_msg = self.get_combined_db_error()


    # DB 연결 성공 여부 확인 함수
    def check_connection(self):
        # [핵심] 이미 연결되어 있고 에러가 없다면 다시 연결하지 않음!
        if self.neo4j and self.chroma and self.db_connect_error_msg is None:
            return True
            
        self.connect_db()
        if self.db_connect_error_msg:
            return False


    # DB 병렬 탐색 함수
    def get_corporate_context(self, query: str, cypher_queries: List[str], center_entity_name: str, search_filter: Optional[SearchFilter] = None) -> DBSearchResponse:
        vector_search_result = self.chroma.search_vector_db(query, search_filter=search_filter)
        graph_search_result = self.neo4j.search_graph_db(cypher_queries, center_entity_name)

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
        
    
    # def find_best_match(self, extracted_name, entity_type):
    #     # 1. 무조건 이 이름으로 정규화되어야 하는 그룹 (alias_map)
    #     # 여기에 적힌 키(Key)가 들어오면 고민하지 않고 값(Value)으로 리턴합니다.
    #     if extracted_name in self.strict_normalization_map:
    #         return self.strict_normalization_map[extracted_name]

    #     # 2. 이프문 제거: entity_type("Company", "Person" 등)을 키값으로 다이렉트 조회
    #     official_names = self.node_names.get(entity_type)
    #     official_embeddings = self.node_embeddings.get(entity_type)

    #     if not official_names or official_embeddings is None:
    #         return None

    #     # 3. 입력된 이름 임베딩화
    #     target_embedding = get_embeddings(self.client, [extracted_name])
        
    #     # 4. 유사도 계산
    #     similarities = cosine_similarity(target_embedding, official_embeddings).flatten()
    #     best_idx = similarities.argmax()

    #     print(f"{extracted_name} : {similarities[best_idx]}")
        
    #     # 임계값 설정
    #     if similarities[best_idx] < 0.6:
    #         return None
            
    #     return official_names[best_idx]