from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from config import Config

def get_vector_db():
    persist_dir = "./chroma_db"
    
    return Chroma(
        persist_directory=persist_dir,
        embedding_function=OpenAIEmbeddings(openai_api_key=Config.OPENAI_API_KEY)
    )