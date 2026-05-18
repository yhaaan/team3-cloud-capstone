from typing import List, Optional
from pydantic import BaseModel, Field
from app.config import Config
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from app.agent.prompts import *
from app.schemas import EntityExtractionData, CypherGenerationResponse


# 엔티티 추출 LLM 응답 형태
class EnitityExtractionResponse(BaseModel):
    data: Optional[EntityExtractionData] = Field(None, description="정상 추출 시 데이터 객체")
    error_msg: Optional[str] = Field(default=None, description="예외 처리 우선순위에 따른 에러 메시지")


class LLMManager:
    def __init__(self):
        # 1. 사용할 모델들을 미리 딱 한 번만 생성해둡니다.
        # 즉각적인 답변 생성, 자연스러운 대화, 빠른 속도, 일반적인 수준의 논리 -> 최종 답변 생성에 사용(빠르고 자연스러운 대화 제공)
        self.gpt4o = ChatOpenAI(
            model="gpt-4o",
            api_key=Config.OPENAI_API_KEY,
            temperature=0,  # 정확도를 위해 0으로 설정
            seed=42 # 똑같은 질문에 대해 똑같은 답변을 내기 위해 고정
        )

        # 추론 특화, 내부 추론(CoT) 과정을 거친 후 답변, 추론 시간에 따라 약간의 지연 발생 가능 -> 질문 재구성, 엔티티 추출, 사이퍼 쿼리 생성에 사용(틀리면 안되는 논리적인 작업)
        self.gpto4mini = ChatOpenAI(
            model="o4-mini",
            api_key=Config.OPENAI_API_KEY,
            seed=42 # 똑같은 질문에 대해 똑같은 답변을 내기 위해 고정
        )

        # 하위 쿼리 생성용 llm 체인 정의
        self.query_planner_prompt = ChatPromptTemplate.from_template(QUERY_PLANNER_PROMPT)
        self.query_planner_chain = self.query_planner_prompt | self.gpto4mini

        # DB 탐색 후 정보 추출(요약 정리)용 llm 체인 정의
        self.info_extraction_prompt = ChatPromptTemplate.from_template(INFO_EXTRACTION_PROMPT)
        self.info_extraction_chain = self.info_extraction_prompt | self.gpto4mini

        # 엔티티 추출용 llm 체인 정의
        self.entity_extraction_llm = self.gpto4mini.with_structured_output(EnitityExtractionResponse) # 응답 형태 지정
        self.entity_extraction_prompt = ChatPromptTemplate.from_template(ENTITY_EXTRACTION_PROMPT)
        self.entity_extraction_chain = self.entity_extraction_prompt | self.entity_extraction_llm

        # 사이퍼 쿼리 생성용 llm 체인 정의
        self.cypher_generation_llm = self.gpto4mini.with_structured_output(CypherGenerationResponse) # 응답 형태 지정
        self.cypher_generation_prompt = ChatPromptTemplate.from_template(CYPHER_GENERATION_PROMPT)
        self.cypher_generation_chain = self.cypher_generation_prompt | self.cypher_generation_llm

        # 최종 답변 생성용 llm 체인 정의
        self.final_response_generation_prompt = ChatPromptTemplate.from_template(FINAL_RESPONSE_GENERATION_PROMPT)
        self.final_response_genration_chain = self.final_response_generation_prompt | self.gpt4o


    # 하위 쿼리 생성 함수
    def generate_sub_queries(self, query: str, history_context: str, extracted_facts: List[str]) -> str:
        response = self.query_planner_chain.invoke({
            "user_query": query,
            "history_context": history_context,
            "extracted_facts": extracted_facts
        })
        return response.content
    

    # DB 탐색 후 정보 추출(요약 정리)용 함수
    def extract_info_from_db_context(self, sub_queries: List[str], raw_contexts: str) -> str:
        response = self.info_extraction_chain.invoke({
            "sub_queries": sub_queries,
            "raw_contexts": raw_contexts
        })
        return response.content


    # 엔티티 추출 함수
    def extract_entities(self, query: str, history_context: str = "") -> EnitityExtractionResponse:
        return self.entity_extraction_chain.invoke({
            "user_query": query,
            "history_context": history_context
        })
    

    # 사이퍼 쿼리 생성 함수
    def generate_cypher(self, query: str, sub_queries: List[str], entity_extraction_data: EntityExtractionData) -> CypherGenerationResponse:
        # 추출된 엔티티는 json으로 변환하여 프롬포트에 주입
        entity_extraction_json = entity_extraction_data.model_dump_json(indent=2) 
        return self.cypher_generation_chain.invoke({
            "user_query": query,
            "sub_queries": sub_queries,
            "entity_extraction_data": entity_extraction_json
        })
    

    # 최종 답변 생성 함수
    def generate_final_response(self, query: str, vector_context: str, graph_context: str, history_context: str = "") -> str:
        response = self.final_response_genration_chain.invoke({
            "user_query": query,
            "vector_context": vector_context,
            "graph_context": graph_context,
            "history_context": history_context
        })
        return response.content


