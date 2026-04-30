from typing import Any, Dict, List

from pydantic import BaseModel
from app.agent.db_handler import VectorHandler, Neo4jHandler 

class DBSearchResponse(BaseModel):
    vector_context: str
    graph_context: List[Dict[str, Any]]

class KnowledgeRetriever:
    def __init__(self):
        self.chroma = VectorHandler()
        self.neo4j = Neo4jHandler()

    # DB 병렬 탐색 함수
    def get_corporate_context(self, query: str, cypher_query: str) -> DBSearchResponse:
        vector_search_result = self.chroma.search_vector_db(query)
        graph_search_result = self.neo4j.search_graph_db(cypher_query)
        
        return DBSearchResponse(
            vector_context=vector_search_result,
            graph_context=graph_search_result
        )