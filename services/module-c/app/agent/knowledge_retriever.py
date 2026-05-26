import os
from pathlib import Path
from typing import List, Optional
import numpy as np
from openai import OpenAI
from pydantic import BaseModel
from sklearn.metrics.pairwise import cosine_similarity
from app.agent.db_handler import VectorHandler, Neo4jHandler 
from app.schemas import *
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
        
        # 데이터를 담을 딕셔너리 초기화
        self.node_embeddings = {}
        self.node_names = {}

        self.check_connection()
    

    # DB 연결 함수
    def connect_db(self):
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


    # 🟢 1. 순수 벡터 DB 탐색 메서드
    def get_vector_context(self, query: str, search_filter: Optional[SearchFilter] = None) -> str:
        """오직 Chroma DB에서 텍스트 청크만 검색하여 컨텍스트 문자열 반환"""
        try:
            vector_search_result = self.chroma.search_vector_db(query, search_filter=search_filter)
            return vector_search_result if vector_search_result else "조회된 벡터 데이터 없음"
        except Exception as e:
            # 개별 에러 로깅 처리
            print(f"[Vector DB Error] {e}")
            return f"벡터 DB 조회 중 에러 발생: {str(e)}"

    # 🔵 2. 순수 그래프 DB 탐색 메서드
    def get_graph_context(self, cypher_queries: List[CypherQuery], center_entity_name: str) -> GraphDBSearchResponse:
        """오직 Neo4j에서 Cypher 쿼리를 실행하여 구조화 데이터 및 텍스트 반환"""
        try:
            graph_search_result = self.neo4j.search_graph_db(cypher_queries, center_entity_name)
            return graph_search_result
        except Exception as e:
            print(f"[Graph DB Error] {e}")
            # 에러 발생 시 빈 구조체나 에러 메시지를 담아서 반환
            return GraphDBSearchResponse(
                graph_context=f"그래프 DB 조회 중 에러 발생: {str(e)}",
                graph_structured_data=[],
                center_id=None,
                cypher_query_purposes=[]
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