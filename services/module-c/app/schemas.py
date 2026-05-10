from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

# region RelationGraph (그래프 DB 탐색 결과 구조화 데이터)
# 노드 구조
class RelationNode(BaseModel):
    id: str
    name: str

# 엣지 구조
class RelationLink(BaseModel):
    source: str
    target: str
    relation: str

# 전체 구조화 데이터 구조
class RelationGraph(BaseModel):
    center: Optional[str] = None # 중앙 노드 이름
    nodes: List[RelationNode]
    links: List[RelationLink]
# endregion


# region 채팅 데이터 구조
# 채팅 요청 데이터
class ChatRequest(BaseModel):
    query: str # 사용자의 자연어 질문
    rag_on: bool # RAG 사용 여부
    recent_history_str: Optional[List[Dict[str, str]]] = [] # 프론트에서 보낸 최근 대화 문자열(최근 질문 제외하고 2쌍)

# 채팅 응답 데이터
class ChatResponse(BaseModel):
    answer: str # 최종 자연어 답변
    has_center: bool # 중앙 노드 있는지 여부
    graph_data: Optional[RelationGraph] = None # 그래프 DB 탐색 결과를 시각화하기 좋게 구조화한 데이터
# endregion


# region 엔티티 추출 
# 기업명/인물명 엔티티 데이터 구조
class NamedEntityData(BaseModel):
    companies: List[str] = Field(default_factory=list, description="추출된 상장사/법인명 리스트")
    people: List[str] = Field(default_factory=list, description="추출된 인물명 리스트")

# 관계 필터 데이터 구조
class RelationFilter(BaseModel):
    subject: str = Field(description="관계의 주체")
    relation_type: str = Field(description="관계 종류")
    object: str = Field(description="관계의 대상")

# 엔티티 추출 데이터 구조
class EntityExtractionData(BaseModel):
    query_intent: str = Field(description="질문의 의도")
    named_entities: NamedEntityData
    relation_filters: List[RelationFilter] = Field(default_factory=list)
    time_info: Optional[str] = Field(default=None, description="명시된 시간 정보")
# endregion


# 그래프 DB 탐색 응답 데이터
class GraphDBSearchResponse(BaseModel):
    graph_context: str
    graph_structured_data: List[Dict[str, Any]] = Field(default_factory=list)