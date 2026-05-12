import os
from typing import Optional
import numpy as np
from openai import OpenAI
from pydantic import BaseModel
from sklearn.metrics.pairwise import cosine_similarity
from app.agent.db_handler import VectorHandler, Neo4jHandler 
from app.schemas import GraphDBSearchResponse
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
        self.company_node_names = []
        self.person_node_names = []
        self.company_embeddings = None
        self.person_embeddings = None

        self.check_connection()
    

    # DB 연결 함수
    def connect_db(self):
        # API 호출 대신 저장된 파일을 로드
        try:
            self.company_embeddings = np.load('../../services/module-c/company_embeddings.npy')
            self.company_node_names = np.load('../../services/module-c/company_names.npy').tolist()
            self.person_embeddings = np.load('../../services/module-c/person_embeddings.npy')
            self.person_node_names = np.load('../../services/module-c/person_names.npy').tolist()
        except FileNotFoundError:
            print("임베딩 파일이 없습니다. pre_embed.py를 먼저 실행하세요.")
            self.db_connect_error_msg = "Embedding files not found."
            return

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
        

    def find_best_match(self, extracted_name, entity_type):
        # 1. 무조건 이 이름으로 정규화되어야 하는 그룹 (alias_map)
        # 여기에 적힌 키(Key)가 들어오면 고민하지 않고 값(Value)으로 리턴합니다.
        strict_normalization_map = {
            "삼성": "삼성전자",
            "삼성전자": "삼성전자",
            "SK하이닉스": "SK하이닉스",
            "현대": "현대차",
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

        if extracted_name in strict_normalization_map:
            return strict_normalization_map[extracted_name]

        # 2. 임베딩 데이터 선택
        if entity_type == "Company":
            official_names = self.company_node_names
            official_embeddings = self.company_embeddings
        else:
            official_names = self.person_node_names
            official_embeddings = self.person_embeddings

        if not official_names or official_embeddings is None:
            return None

        # 3. 입력된 이름 임베딩화
        target_embedding = get_embeddings(self.client, [extracted_name])
        
        # 4. 유사도 계산
        similarities = cosine_similarity(target_embedding, official_embeddings).flatten()
        best_idx = similarities.argmax()

        print(f"{extracted_name} : {similarities[best_idx]}")
        
        # 임계값 설정 (OpenAI 3-small 기준 0.4~0.45가 적당)
        if similarities[best_idx] < 0.42:
            return None
            
        return official_names[best_idx]