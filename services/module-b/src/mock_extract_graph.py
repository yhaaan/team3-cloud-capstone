from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = BASE_DIR.parent / "tests" / "fixtures"
OUTPUT_DIR = BASE_DIR.parent / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_json_file(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def mock_extract_graph(doc: dict[str, Any]) -> dict[str, Any]:
    """
    실제 LLM 대신 규칙 기반으로 예시 그래프 JSON 생성
    """
    content = doc.get("content", "")
    source_id = doc.get("source_id", "unknown")

    entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    if "카카오" in content:
        entities.append({"id": "company_kakao", "type": "Company", "name": "카카오"})
    if "A사" in content:
        entities.append({"id": "company_a", "type": "Company", "name": "A사"})
    if "AI" in content:
        entities.append({"id": "industry_ai", "type": "Industry", "name": "AI"})

    if "카카오" in content and "A사" in content and "인수" in content:
        relations.append(
            {
                "type": "ACQUIRES",
                "from": "company_kakao",
                "to": "company_a",
                "evidence": "카카오는 2026년 3월 20일 A사 인수를 발표했다."
            }
        )

    if "카카오" in content and "AI" in content:
        relations.append(
            {
                "type": "BELONGS_TO",
                "from": "company_kakao",
                "to": "industry_ai",
                "evidence": "이번 인수는 AI 사업 강화를 위한 전략적 결정이다."
            }
        )

    return {
        "source_id": source_id,
        "entities": deduplicate_entities(entities),
        "relations": relations,
    }


def deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    results = []

    for entity in entities:
        key = (entity["id"], entity["type"], entity["name"])
        if key not in seen:
            seen.add(key)
            results.append(entity)

    return results


if __name__ == "__main__":
    doc = load_json_file(FIXTURE_DIR / "sample_news_01.json")
    graph_data = mock_extract_graph(doc)

    output_path = OUTPUT_DIR / "sample_news_01_graph.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)

    print(f"[OK] 그래프 JSON 생성 완료: {output_path}")