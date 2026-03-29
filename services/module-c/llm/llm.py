import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

def get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    return genai.Client(api_key=api_key)

def call_llm(prompt: str):
    client = get_client()

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    return response.text