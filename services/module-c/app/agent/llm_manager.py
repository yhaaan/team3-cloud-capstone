from typing import Optional
from pydantic import BaseModel, Field
from app.config import Config
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from app.agent.prompts import ENTITY_EXTRACTION_PROMPT, CYPHER_GENERATION_PROMPT, FINAL_RESPONSE_GENERATION_PROMPT
from app.schemas import EntityExtractionData

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
            temperature=0  # 정확도를 위해 0으로 설정
        )

        # 추론 특화, 내부 추론(CoT) 과정을 거친 후 답변, 추론 시간에 따라 약간의 지연 발생 가능 -> 엔티티 추출, 사이퍼 쿼리 생성에 사용(틀리면 안되는 논리적인 작업)
        self.gpto4mini = ChatOpenAI(
            model="o4-mini",
            api_key=Config.OPENAI_API_KEY,
        )

        # 엔티티 추출용 llm 체인 정의
        self.entity_extraction_llm = self.gpto4mini.with_structured_output(EnitityExtractionResponse)
        self.entity_extraction_prompt = ChatPromptTemplate.from_template(ENTITY_EXTRACTION_PROMPT)
        self.entity_extraction_chain = self.entity_extraction_prompt | self.entity_extraction_llm

        # 사이퍼 쿼리 생성용 llm 체인 정의
        self.cypher_generation_prompt = ChatPromptTemplate.from_template(CYPHER_GENERATION_PROMPT)
        self.cypher_generation_chain = self.cypher_generation_prompt | self.gpto4mini

        # 최종 답변 생성용 llm 체인 정의
        self.final_response_generation_prompt = ChatPromptTemplate.from_template(FINAL_RESPONSE_GENERATION_PROMPT)
        self.final_response_genration_chain = self.final_response_generation_prompt | self.gpt4o


    # 엔티티 추출 함수
    def extract_entities(self, query: str) -> EnitityExtractionResponse:
        return self.entity_extraction_chain.invoke({"user_query": query})
    

    # 사이퍼 쿼리 생성 함수
    def generate_cypher(self, query: str, entity_extraction_data: EntityExtractionData) -> str:
        # 추출된 엔티티는 json으로 변환하여 프롬포트에 주입
        entity_extraction_json = entity_extraction_data.model_dump_json(indent=2) 
        response = self.cypher_generation_chain.invoke({
            "user_query": query,
            "entity_extraction_data": entity_extraction_json
        })

        # 깔끔하게 가공
        raw_cypher_query = response.content.strip()
        cypher_query = raw_cypher_query.replace("```cypher", "").replace("```", "").strip()  # LLM이 가끔 따옴표(```cypher)를 붙여줄 때가 있어서 제거해주는 전처리 필요

        return cypher_query
    

    # 최종 답변 생성 함수
    def generate_final_response(self, query: str, vector_context: str, graph_context: str) -> str:
        response = self.final_response_genration_chain.invoke({
            "user_query": query,
            "vector_context": vector_context,
            "graph_context": graph_context
        })
        return response.content


