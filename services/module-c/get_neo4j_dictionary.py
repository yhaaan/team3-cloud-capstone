# Neo4j가 업데이트 될 때마다 백엔드 서버 실행 전 현재 파일 실행!

import json
import os
from app.agent.db_handler import Neo4jHandler


def save_neo4j_dictionary():
    # 백엔드 서버(Agent)와 동일한 경로 설정
    BASE_PATH = 'services/module-c/neo4j_label_dictionaries'

    # 1. Neo4j Handler 생성
    neo4j = Neo4jHandler() 
    
    # 2. [Neo4j 라벨명 : 저장할 npy 파일 접두사] 맵핑 테이블 정의 (앞서 고친 백엔드와 동기화)
    label_to_file = {
        "Company": "company",
        "Industry": "industry",
        "AffiliateGroup": "affiliate_group",
        "ProductService": "product_service"
    }

    print("🚀 그래프 DB 노드 데이터 기반 사전(Dictionary) 캐싱 작업 시작...\n")

    try:
        # 저장 디렉토리 보장
        os.makedirs(BASE_PATH, exist_ok=True)

        for label, file_prefix in label_to_file.items():
            print(f"🔄 [{label}] 노드 이름을 DB에서 가져오는 중...")
            node_names = neo4j.get_node_names_by_label(label)

            if node_names:
                # 🌟 리스트 자체를 순수 JSON 파일로 저장
                file_path = f'{BASE_PATH}/{file_prefix}_dictionary.json'
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    # indent=2는 개발자 가독성용으로 좋으니 그대로 유지하되, 
                    # 백엔드가 읽어갈 때 어차피 json.dumps로 공백을 싹 압축하므로 베스트입니다.
                    json.dump(node_names, f, ensure_ascii=False, indent=2)
                
                print(f"✅ 캐싱 완료: {file_prefix}_dictionary.json (총 {len(node_names)}개)\n")
            else:
                print(f"⚠️ [{label}] 데이터가 DB에 없어 건너뜁니다.\n")

        print("🎉 모든 라벨에 대한 텍스트 딕셔너리 동기화가 완료되었습니다!")

    except Exception as e:
        print(f"❌ 동기화 중 에러 발생: {e}")
        
    finally:
        # 🌟 3. 커넥션 풀을 안전하게 닫아주기 (Neo4jHandler에 close 메드가 있다고 가정)
        if hasattr(neo4j, "close"):
            neo4j.close()
            print("🔌 Neo4j 커넥션이 안전하게 종료되었습니다.")

if __name__ == "__main__":
    save_neo4j_dictionary()