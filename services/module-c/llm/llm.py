import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0
)

def call_llm(prompt: str):
    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        print(f"LLM 호출 중 에러 발생: {e}")
        return "답변을 생성하는 중에 문제가 발생했습니다."