from vector.vectorstore import get_vector_db
from graph.neo4j_db import get_graph
from llm.llm import call_llm

# 엔티티 추출 프롬프트
ENTITY_EXTRACTION_PROMPT = """
당신은 지식 그래프 전문가입니다. 사용자의 질문에서 핵심이 되는 '기업명' 또는 '인물명'을 추출하세요.
질문: {query}
결과 예시: 삼성전자, 애플 (콤마로 구분해서 단어만 출력하세요)
"""

# 사이퍼 쿼리 추출 프롬프트
CYPHER_GENERATION_PROMPT = """
당신은 Neo4j Cypher 쿼리 생성기입니다. 
아래 규칙을 반드시 지키세요:
1. 답변에 설명이나 인사말을 절대 넣지 마세요.
2. 오직 Cypher 쿼리 문자열만 출력하세요.
3. 예외 상황이라도 자연어로 대답하지 마세요.

엔티티: {entities}
질문: {query}

쿼리 예시: MATCH (c:Company {{name: '{entities}'}}) RETURN c
"""

# 전역에서 한 번만 가져옴 (매번 DB와 연결하는 것은 비효율적이기 때문)
db = get_vector_db()
graph = get_graph()

def vector_tool(query):
    docs = db.similarity_search(query, k=3)
    # 가공 과정 (Document 객체에서 텍스트만 추출)
    return [doc.page_content for doc in docs]

def graph_tool(query: str):
    # 1단계: 엔티티 추출 (Entity Extraction)
    entities = call_llm(ENTITY_EXTRACTION_PROMPT.format(query=query))
    print(f"[Step 1] 추출된 엔티티: {entities}")

    # 2단계: Cypher 쿼리 생성 (Text-to-Cypher)
    cypher_query = call_llm(CYPHER_GENERATION_PROMPT.format(entities=entities, query=query))
    # [중요] LLM이 가끔 따옴표(```cypher)를 붙여줄 때가 있어서 제거해주는 전처리가 필요합니다.
    cypher_query = cypher_query.replace("```cypher", "").replace("```", "").strip()
    print(f"[Step 2] 생성된 Cypher 쿼리: {cypher_query}")

    # 3단계: graph.query() 사용하여 실행
    try:
        result = graph.query(cypher_query)
        return result
    except Exception as e:
        print(f"DB 실행 에러: {e}")
        return "그래프 조회 중 오류가 발생했습니다."