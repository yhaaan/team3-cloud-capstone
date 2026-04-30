from vectorstore import get_vector_db
from langchain_core.documents import Document
import shutil
import os

def add_sample_data():
    persist_dir = "./chroma_db"

    # 기존 데이터 폴더가 있으면 삭제 (초기화)
    if os.path.exists(persist_dir):
        shutil.rmtree(persist_dir)
        print(f"기존 DB({persist_dir})를 삭제하고 초기화합니다.")

    db = get_vector_db()
    
    # 1. 샘플 데이터 작성 (교수님께 보여줄 비정형 데이터)
    samples = [
        Document(
            page_content="삼성전자는 2026년까지 AI 반도체 분야에 10조 원을 투자할 계획이다.",
            metadata={"source": "경제뉴스", "date": "2026-03-01"}
        ),
        Document(
            page_content="애플과 삼성전자는 차세대 디스플레이 공급 계약을 체결하며 협력을 강화하고 있다.",
            metadata={"source": "산업리포트", "date": "2026-03-15"}
        ),
        Document(
            page_content="기업 분석 결과, A사와 B사는 전략적 파트너십 관계를 유지하고 있는 것으로 나타났다.",
            metadata={"source": "기업공시", "date": "2026-03-20"}
        )
    ]
    
    # 2. DB에 저장 (이때 embedding.py에 설정한 모델이 숫자로 바꿔서 저장함)
    db.add_documents(samples)
    print("성공: 벡터 DB에 샘플 데이터가 저장되었습니다!")

if __name__ == "__main__":
    add_sample_data()