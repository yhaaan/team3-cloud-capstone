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
    center: Optional[str] = None # 중앙 노드 id
    nodes: List[RelationNode]
    links: List[RelationLink]
# endregion


# region 채팅 데이터 구조
# 채팅 요청 데이터
class ChatRequest(BaseModel):
    question: str # 사용자의 자연어 질문
    rag_on: bool # RAG 사용 여부
    recent_history: Optional[List[Dict[str, str]]] = [] # 프론트에서 보낸 최근 대화 문자열(최근 질문 제외하고 2쌍)

# 채팅 응답 데이터
class ChatResponse(BaseModel):
    answer: str # 최종 자연어 답변
    how: Optional[str] = None # 그래프 종류
    graph: Optional[RelationGraph] = None # 그래프 DB 탐색 결과를 시각화하기 좋게 구조화한 데이터
# endregion


# region 엔티티 추출 
# # 기업명/인물명 엔티티 데이터 구조
# class NamedEntityData(BaseModel):
#     companies: List[str] = Field(default_factory=list, description="추출된 상장사/법인명 리스트")
#     people: List[str] = Field(default_factory=list, description="추출된 인물명 리스트")


# endregion


# region 응답 형태
# 엔티티 추출 데이터 구조
class EntityExtractionData(BaseModel):
    companies: List[str] = Field(default_factory=list, description="추출된 상장사/법인명 리스트")
    industries: List[str] = Field(default_factory=list, description="추출된 산업군 명칭 리스트")
    products_services: List[str] = Field(default_factory=list, description="추출된 제품/서비스 명칭 리스트")
    affiliate_groups: List[str] = Field(default_factory=list, description="추출된 계열사 그룹(예: 현대자동차그룹) 명칭 리스트")
    people: List[str] = Field(default_factory=list, description="추출된 인물명 리스트")


# 엔티티 추출 LLM 응답 형태
class EnitityExtractionResponse(BaseModel):
    named_entities: Optional[EntityExtractionData] = Field(None, description="라벨별로 정확히 분류된 고유명사 객체")
    error_msg: Optional[str] = Field(default=None, description="예외 처리 우선순위에 따른 에러 메시지")


# 엔티티 정규화 LLM 응답 형태
class EnitityNormalizationResponse(BaseModel):
    companies: List[str] = Field(default_factory=list, description="기업 사전 JSON에 매칭된 정식 상장사명 리스트")
    industries: List[str] = Field(default_factory=list, description="산업 사전 JSON에 매칭된 표준 산업명 리스트")
    products_services: List[str] = Field(default_factory=list, description="제품/서비스 사전 JSON에 매칭된 표준 제품명 리스트")
    affiliate_groups: List[str] = Field(default_factory=list, description="계열사 그룹 사전에 매칭된 표준 대기업 그룹명 리스트")
    people: List[str] = Field(default_factory=list, description="성+이름으로 정형화된 인물명 리스트")


# 하위 질문에 대응되는 사이퍼 쿼리 리스트    
class SubCypherQueries(BaseModel):
    sub_cypher_queries: List[str] = Field(description="하위 질문에 대한 Neo4j에서 실행할 사이퍼 쿼리 리스트")


# 사이퍼 쿼리 생성 LLM 응답 형태
class CypherGenerationResponse(BaseModel):
    cypher_queries: List[SubCypherQueries] = Field(description="하위 질문별 Neo4j에서 실행할 사이퍼 쿼리 리스트")
    center_entity_name: str = Field(description="이 검색의 중심이 되는 핵심 엔티티 이름 (가장 중요한 키워드 1개)")


# 그래프 DB 탐색 응답 데이터
class GraphDBSearchResponse(BaseModel):
    center_id: str
    graph_context: str
    graph_structured_data: List[Dict[str, Any]] = Field(default_factory=list)


class SearchFilter(BaseModel):
    # stock_code: Optional[str] = Field(None, description="주식 코드 (005380 등)")
    company_name: Optional[str] = Field(None, description="회사명 (현대차 등)")
    dataset_label: Optional[str] = Field(None, description="문서 종류 (임원 현황 등)")
    document_type: Optional[str] = Field(None, description="dart, news 등")


class SubQuery(BaseModel):
    query: str = Field(..., description="수행할 하위 질문")
    filter: Optional[SearchFilter] = Field(None, description="벡터 검색 시 사용할 필터 조건")


class QueryPlanResponse(BaseModel):
    sub_queries: List[SubQuery] = Field(..., description="계획된 하위 질문 리스트")