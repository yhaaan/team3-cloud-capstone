from langchain_neo4j import Neo4jGraph
import os
from dotenv import load_dotenv

load_dotenv()

def get_graph():
    return Neo4jGraph(
        url="bolt://localhost:7687",
        username="neo4j",
        password=os.getenv("NEO4J_PASSWORD")
    )