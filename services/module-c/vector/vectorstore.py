from langchain_chroma import Chroma
from vector.embedding import get_embedding

def get_vector_db():
    embedding = get_embedding()
    persist_dir = "./chroma_db"
    
    return Chroma(
        persist_directory=persist_dir,
        embedding_function=embedding
    )