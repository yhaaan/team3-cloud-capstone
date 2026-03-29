from langchain_chroma import Chroma
from rag.embedding import get_embedding

def get_vector_db():
    embedding = get_embedding()
    
    return Chroma(
        persist_directory="./chroma_db",
        embedding_function=embedding
    )