from typing import List, Optional
from pydantic import BaseModel, Field
from app.config import Config
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from app.agent.prompts import *
from app.schemas import *


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

        # 일관된 응답을 얻기 위해 temperature가 있고 빠른 gpt4omini 사용
        self.gpt4omini = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=Config.OPENAI_API_KEY,
            temperature=0,
            top_p=0.01,
            seed=42 # 똑같은 질문에 대해 똑같은 답변을 내기 위해 고정
        )

        # 질문 재구성용 llm 체인 정의
        self.query_rewrite_llm = self.gpt4omini.with_structured_output(QueryRewriteResponse) # 응답 형태 지정
        self.query_rewrite_prompt = ChatPromptTemplate.from_template(QUERY_REWRITE_PROMPT)
        self.query_rewrite_chain = self.query_rewrite_prompt | self.query_rewrite_llm

        # 엔티티 추출용 llm 체인 정의
        self.entity_extraction_llm = self.gpt4omini.with_structured_output(EnitityExtractionResponse) # 응답 형태 지정
        self.entity_extraction_prompt = ChatPromptTemplate.from_template(ENTITY_EXTRACTION_PROMPT)
        self.entity_extraction_chain = self.entity_extraction_prompt | self.entity_extraction_llm

        # 하위 쿼리 생성용 llm 체인 정의
        self.query_planner_llm = self.gpt4omini.with_structured_output(QueryPlanResponse) # 응답 형태 지정
        self.query_planner_prompt = ChatPromptTemplate.from_template(VECTOR_QUERY_PLANNER_PROMPT)
        self.query_planner_chain = self.query_planner_prompt | self.query_planner_llm

        # 사이퍼 쿼리 생성용 llm 체인 정의
        self.cypher_generation_llm = self.gpt4omini.with_structured_output(CypherGenerationResponse) # 응답 형태 지정
        self.cypher_generation_prompt = ChatPromptTemplate.from_template(CYPHER_GENERATION_PROMPT)
        self.cypher_generation_chain = self.cypher_generation_prompt | self.cypher_generation_llm

        # 최종 답변 생성용 llm 체인 정의
        self.final_response_generation_prompt = ChatPromptTemplate.from_template(FINAL_RESPONSE_GENERATION_PROMPT)
        self.final_response_genration_chain = self.final_response_generation_prompt | self.gpt4o


    # 질문 재구성 함수
    async def rewrite_query(self, query: str, history_context: str = "") -> QueryRewriteResponse:
        return await self.query_rewrite_chain.ainvoke({
            "user_query": query,
            "history_context": history_context
        })


    # 엔티티 추출 함수
    async def extract_entities(self, query: str) -> EnitityExtractionResponse:
        return await self.entity_extraction_chain.ainvoke({
            "user_query": query
        })
    

    # 하위 쿼리 생성 함수
    async def generate_sub_queries(self, query: str, extracted_company_names: List[str]) -> QueryPlanResponse:
        return await self.query_planner_chain.ainvoke({
            "user_query": query,
            "extracted_company_names": extracted_company_names
        })
    

    # 사이퍼 쿼리 생성 함수
    async def generate_cypher(self, query: str, entity_extraction_data: EntityExtractionData) -> CypherGenerationResponse:
        # 추출된 엔티티는 json으로 변환하여 프롬포트에 주입
        entity_extraction_json = entity_extraction_data.model_dump_json(indent=2) 
        return await self.cypher_generation_chain.ainvoke({
            "user_query": query,
            "entity_extraction_data": entity_extraction_json
        })
    

    # 최종 답변 생성 함수
    async def generate_final_response(self, query: str, vector_context: str, graph_context: str, cypher_query_purposes = "", history_context: str = "") -> str:
        response = await self.final_response_genration_chain.ainvoke({
            "user_query": query,
            "vector_context": vector_context,
            "graph_context": graph_context,
            "cypher_query_purposes": cypher_query_purposes,
            "history_context": history_context
        })
        return response.content


