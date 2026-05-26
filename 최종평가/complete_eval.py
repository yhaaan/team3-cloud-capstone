import asyncio
import json
import os
import httpx
from tqdm.asyncio import tqdm

# 경로 정의
EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(EVAL_DIR, "rag_eval_questions.jsonl")
TEMPLATE_FILE = os.path.join(EVAL_DIR, "rag_eval_answers_template.jsonl")
FINAL_FILE = os.path.join(EVAL_DIR, "rag_eval_answers_final.jsonl")

API_URL = "http://127.0.0.1:8000/chat"


async def fetch_answer(
    client: httpx.AsyncClient, question: str, rag_on: bool
) -> str:
    payload = {
        "question": question,
        "rag_on": rag_on,
        "recent_history": [],
    }
    try:
        # 안정성을 위해 타임아웃을 180초로 대폭 확장
        response = await client.post(API_URL, json=payload, timeout=180.0)
        if response.status_code == 200:
            return response.json().get("answer", "")
        else:
            return f"[Error] HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return f"[Error] Request Failed: {str(e)}"


async def main():
    # 1. 원본 질문 데이터 매핑
    questions_map = {}
    if os.path.exists(QUESTIONS_FILE):
        with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    questions_map[data["id"]] = data["question"]

    # 2. 템플릿(전체 90개 기준 백업본) 로드
    if not os.path.exists(TEMPLATE_FILE):
        print(f"❌ 기준이 되는 템플릿 파일이 없습니다: {TEMPLATE_FILE}")
        return

    all_templates = []
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_templates.append(json.loads(line))

    # 3. 기존에 중간까지 진행되던 결과 파일 로드 및 분류
    existing_records = {}
    if os.path.exists(FINAL_FILE):
        with open(FINAL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    # 유일한 키 조합 매핑 (ID + 모드)
                    key = (rec["question_id"], rec["system_type"])
                    existing_records[key] = rec

    # 4. 해야 할 작업 분류 (에러 항목 또는 미진행 항목 추출)
    tasks_to_run = []  # 새로 API 호출해야 할 항목들
    final_results_pool = []  # 최종 파일에 유지/복구되어 들어갈 풀

    for tmp in all_templates:
        q_id = tmp["question_id"]
        s_type = tmp["system_type"]
        key = (q_id, s_type)

        question = tmp.get("question") or questions_map.get(q_id, "")

        # 기존 결과 파일에 이미 존재할 때
        if key in existing_records:
            current_rec = existing_records[key]
            # 에러가 섞여 있다면 갱신 대상으로 추가
            if "[Error]" in current_rec.get("answer", ""):
                tasks_to_run.append(
                    {"task": tmp, "is_new": False, "question": question}
                )
            else:
                # 정상 답변은 호출하지 않고 그대로 보존 풀에 보관
                final_results_pool.append(current_rec)
        else:
            # 기존 결과 파일에 아예 없다면 (중단 이후 누락된 항목) 갱신 대상으로 추가
            tasks_to_run.append(
                {"task": tmp, "is_new": True, "question": question}
            )

    if not tasks_to_run:
        print("✨ 축하합니다! 모든 데이터가 에러 없이 90개 완벽하게 채워져 있습니다.")
        return

    print(
        f"📊 상태 점검: 보존할 정상 답변 {len(final_results_pool)}개 | 다시 채워야 할 작업(에러+누락) {len(tasks_to_run)}개"
    )
    print("🔄 안전 모드로 복구 및 남은 평가 연산을 재개합니다...")

    # 5. 안전하게 동시 요청을 1개로 제한하여 순차 처리 (Rate Limit 원천 차단)
    semaphore = asyncio.Semaphore(1)

    async def bound_worker(item, client):
        async with semaphore:
            await asyncio.sleep(1.0)  # 요청 사이에 1초의 최소 휴식시간 부여

            task = item["task"]
            q_id = task["question_id"]
            s_type = task["system_type"]
            question = item["question"]
            rag_on = True if s_type == "rag_on" else False

            # API 호출
            new_answer = await fetch_answer(client, question, rag_on)

            return {
                "question_id": q_id,
                "system_type": s_type,
                "question": question,
                "answer": new_answer,
            }

    async with httpx.AsyncClient() as client:
        tasks = [bound_worker(item, client) for item in tasks_to_run]

        for coro in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Completing RAG Eval",
        ):
            new_res = await coro
            final_results_pool.append(new_res)

            # 실시간 정렬 후 파일 덮어쓰기 (중간에 끊겨도 데이터는 무조건 안전)
            sorted_results = sorted(
                final_results_pool,
                key=lambda x: (
                    x["question_id"],
                    0 if x["system_type"] == "rag_on" else 1,
                ),
            )

            with open(FINAL_FILE, "w", encoding="utf-8") as f_out:
                for r in sorted_results:
                    f_out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"✨ [성공] 총 90개의 평가 셋이 정렬되어 완벽히 저장되었습니다: {FINAL_FILE}")


if __name__ == "__main__":
    asyncio.run(main())