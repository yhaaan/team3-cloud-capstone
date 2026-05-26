import asyncio
import json
import os
import httpx
from tqdm.asyncio import tqdm

# 경로 정의
EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(EVAL_DIR, "rag_eval_questions.jsonl")
TEMPLATE_FILE = os.path.join(EVAL_DIR, "rag_eval_answers_template.jsonl")
OUTPUT_FILE = os.path.join(EVAL_DIR, "rag_eval_answers_final.jsonl")

# FastAPI 서버 주소 (서버를 먼저 켜두셔야 합니다)
API_URL = "http://127.0.0.1:8000/chat"


async def fetch_answer(
    client: httpx.AsyncClient, question: str, rag_on: bool
) -> str:
    """FastAPI /chat 엔드포인트로 요청을 보내 답변을 받아옵니다."""
    payload = {
        "question": question,
        "rag_on": rag_on,
        "recent_history": [],  # 단발성 질문 평가이므로 빈 배열 전달
    }
    try:
        # LLM 연산 및 RAG 검색 시간이 걸릴 수 있으므로 timeout을 120초로 여유 있게 잡음
        response = await client.post(API_URL, json=payload, timeout=120.0)
        if response.status_code == 200:
            return response.json().get("answer", "")
        else:
            return f"[Error] HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return f"[Error] Request Failed: {str(e)}"


async def main():
    # 1. 원본 질문 파일 읽기 (ID 기반 매핑용)
    questions_map = {}
    if not os.path.exists(QUESTIONS_FILE):
        print(f"❌ 질문 파일이 없습니다: {QUESTIONS_FILE}")
        return

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                questions_map[data["id"]] = data["question"]

    # 2. 템플릿 파일 읽어서 작업 큐 생성
    if not os.path.exists(TEMPLATE_FILE):
        print(f"❌ 템플릿 파일이 없습니다: {TEMPLATE_FILE}")
        return

    tasks_to_run = []
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tasks_to_run.append(json.loads(line))

    print(f"🚀 총 {len(tasks_to_run)}개의 평가 태스크를 로드했습니다.")

    # 3. 비동기 HTTP 클라이언트로 순차적(또는 소규모 병렬) 요청 처리
    # LLM API Rate Limit 및 서버 과부하 방지를 위해 세마포어로 동시 요청을 3개로 제한
    semaphore = asyncio.Semaphore(3)

    async def bound_fetch(task, client):
        async with semaphore:
            q_id = task["question_id"]
            system_type = task["system_type"]
            # 템플릿에 질문이 비어있을 경우 원본 질문 매핑
            question = task.get("question") or questions_map.get(q_id, "")

            rag_on = True if system_type == "rag_on" else False

            # API 호출
            answer = await fetch_answer(client, question, rag_on)

            # 결과 객체 반환
            return {
                "question_id": q_id,
                "system_type": system_type,
                "question": question,
                "answer": answer,
            }

    # 파일 저장을 안전하게 하기 위해 에러 발생 시 중간 저장되도록 유도
    results = []
    async with httpx.AsyncClient() as client:
        # tqdm으로 프로그레스 바 표시
        tasks = [bound_fetch(task, client) for task in tasks_to_run]
        for coro in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Evaluating RAG",
        ):
            res = await coro
            results.append(res)

            # 실시간으로 추적 결과 기록 (실행 중 끊겨도 데이터 보존)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f_out:
                for r in results:
                    f_out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"✨ 평가 완료! 결과가 다음 경로에 저장되었습니다:\n{OUTPUT_FILE}")


if __name__ == "__main__":
    # 라이브러리 미설치 시 자동 안내용
    # 실행 전 pip install httpx tqdm 필수
    asyncio.run(main())