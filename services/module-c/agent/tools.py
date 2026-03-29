from rag.vectorstore import get_vector_db
from rag.retriever import retrieve_docs
from graph.neo4j_db import get_graph
from graph.graph_query import query_graph

# 전역에서 한 번만 가져옴 (매번 DB와 연결하는 것은 비효율적이기 때문)
db = get_vector_db()
graph = get_graph()

def vector_tool(query):
    return retrieve_docs(db, query)

def graph_tool():
    result = query_graph(
        graph,
        "MATCH (n)-[r]->(m) RETURN n,r,m LIMIT 5"
    )
    return result