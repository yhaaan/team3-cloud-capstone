# Neo4j가 업데이트 될 때마다 백엔드 서버 실행 전 현재 파일 실행!

import numpy as np
from openai import OpenAI
from app.agent.db_handler import Neo4jHandler
from app.utils import get_embeddings
from app.config import Config

client = OpenAI(api_key=Config.OPENAI_API_KEY)

def save_embeddings():
    # 2. Neo4j Handler만 단독으로 생성
    neo4j = Neo4jHandler() 
    
    # 3. 데이터 가져오기
    print("DB에서 노드 이름을 가져오는 중...")
    company_names = neo4j.get_node_names_by_type("Company")
    person_names = neo4j.get_node_names_by_type("Person")

    # 4. 기업 데이터 처리
    if company_names:
        print(f"기업 {len(company_names)}개 임베딩 중...")
        company_embs = get_embeddings(client, company_names)
        np.save('services/module-c/company_embeddings.npy', company_embs)
        np.save('services/module-c/company_names.npy', np.array(company_names))
    
    # 5. 인물 데이터 처리
    if person_names:
        print(f"인물 {len(person_names)}개 임베딩 중...")
        person_embs = get_embeddings(client, person_names)
        np.save('services/module-c/person_embeddings.npy', person_embs)
        np.save('services/module-c/person_names.npy', np.array(person_names))

    print("완료!")

if __name__ == "__main__":
    save_embeddings()