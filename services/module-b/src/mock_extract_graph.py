from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import validate

from chunking import split_sentences


BASE_DIR = Path(__file__).resolve().parent
MODULE_B_DIR = BASE_DIR.parent
ROOT_DIR = MODULE_B_DIR.parent.parent
TEST_DATA_DIR = MODULE_B_DIR / "tests"
OUTPUT_DIR = MODULE_B_DIR / "outputs"
GRAPH_SCHEMA_PATH = ROOT_DIR / "schemas" / "graph_schema.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

KNOWN_INDUSTRIES = ["AI", "클라우드", "반도체", "게임", "바이오", "엔터테인먼트", "IT"]
RELATION_KEYWORDS = {
    "ACQUIRES": ["인수", "합병"],
    "INVESTS_IN": ["투자", "출자"],
    "APPOINTED_TO": ["선임", "임명"],
    "AFFILIATED_WITH": ["재직", "부회장", "대표이사", "COO", "CEO", "회장"],
}


def load_json_file(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_name(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", "_", value.strip()).strip("_").lower()
    return normalized or "unknown"


def build_entity_id(entity_type: str, name: str) -> str:
    return f"{entity_type.lower()}_{normalize_name(name)}"


def collect_companies(title: str, content: str) -> list[str]:
    companies: list[str] = []

    prefix_match = re.match(r"^\s*([^,]+),", title)
    if prefix_match:
        companies.append(prefix_match.group(1).strip())

    companies.extend(re.findall(r"[A-Z]사", title))

    for known in ["카카오", "네이버", "삼성전자", "LG전자", "SK하이닉스", "현대자동차", "C사"]:
        if known in title or known in content:
            companies.append(known)

    companies.extend(re.findall(r"[A-Z]사", content))

    return deduplicate_strings(companies)


def collect_people(content: str) -> list[dict[str, str]]:
    people: list[dict[str, str]] = []

    for match in re.finditer(r"([가-힣]{2,4})을 신임 ([가-힣A-Za-z()]+)로 선임", content):
        people.append({"name": match.group(1), "role": match.group(2)})

    for match in re.finditer(r"([가-힣]{2,4})은 기존에 ([^.]*)로 재직", content):
        people.append({"name": match.group(1), "role": match.group(2).strip()})

    return deduplicate_people(people)


def collect_industries(content: str) -> list[str]:
    return [industry for industry in KNOWN_INDUSTRIES if industry in content]


def find_evidence_sentence(content: str, keywords: list[str]) -> str:
    for sentence in split_sentences(content):
        if all(keyword in sentence for keyword in keywords):
            return sentence

    for sentence in split_sentences(content):
        if any(keyword in sentence for keyword in keywords):
            return sentence

    return ""


def extract_graph(doc: dict[str, Any]) -> dict[str, Any]:
    title = doc.get("title", "")
    content = doc.get("content", "")
    source_id = doc.get("source_id", "unknown")

    companies = collect_companies(title, content)
    people = collect_people(content)
    industries = collect_industries(content)

    entities: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []

    for company in companies:
        entities.append(
            {"id": build_entity_id("company", company), "type": "Company", "name": company}
        )

    for person in people:
        entities.append(
            {
                "id": build_entity_id("person", person["name"]),
                "type": "Person",
                "name": person["name"],
                "role": person["role"],
            }
        )

    for industry in industries:
        entities.append(
            {"id": build_entity_id("industry", industry), "type": "Industry", "name": industry}
        )

    if len(companies) >= 2 and has_relation_keyword(content, "ACQUIRES"):
        relations.append(
            {
                "type": "ACQUIRES",
                "from": build_entity_id("company", companies[0]),
                "to": build_entity_id("company", companies[1]),
                "evidence": find_evidence_sentence(content, [companies[0], companies[1], "인수"]),
            }
        )

    if len(companies) >= 2 and has_relation_keyword(content, "INVESTS_IN"):
        relations.append(
            {
                "type": "INVESTS_IN",
                "from": build_entity_id("company", companies[0]),
                "to": build_entity_id("company", companies[1]),
                "evidence": find_evidence_sentence(content, [companies[0], companies[1], "투자"]),
            }
        )

    if companies and industries:
        for industry in industries:
            relations.append(
                {
                    "type": "BELONGS_TO",
                    "from": build_entity_id("company", companies[0]),
                    "to": build_entity_id("industry", industry),
                    "evidence": find_evidence_sentence(content, [industry]),
                }
            )

    if companies and people and has_relation_keyword(content, "APPOINTED_TO"):
        relations.append(
            {
                "type": "APPOINTED_TO",
                "from": build_entity_id("person", people[0]["name"]),
                "to": build_entity_id("company", companies[0]),
                "evidence": find_evidence_sentence(content, [people[0]["name"], "선임"]),
            }
        )

    if companies and people and has_relation_keyword(content, "AFFILIATED_WITH"):
        relations.append(
            {
                "type": "AFFILIATED_WITH",
                "from": build_entity_id("person", people[0]["name"]),
                "to": build_entity_id("company", companies[0]),
                "evidence": find_evidence_sentence(content, [people[0]["name"]]),
            }
        )

    graph = {
        "source_id": source_id,
        "entities": deduplicate_entities(entities),
        "relations": [relation for relation in relations if relation["evidence"]],
    }
    validate(instance=graph, schema=load_json_file(GRAPH_SCHEMA_PATH))
    return graph


def has_relation_keyword(content: str, relation_type: str) -> bool:
    return any(keyword in content for keyword in RELATION_KEYWORDS[relation_type])


def deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    results: list[dict[str, Any]] = []

    for entity in entities:
        key = (entity["id"], entity["type"], entity["name"])
        if key not in seen:
            seen.add(key)
            results.append(entity)

    return results


def deduplicate_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            results.append(value)
    return results


def deduplicate_people(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    results: list[dict[str, str]] = []
    for value in values:
        key = (value["name"], value["role"])
        if key not in seen:
            seen.add(key)
            results.append(value)
    return results


if __name__ == "__main__":
    for file_path in sorted(TEST_DATA_DIR.glob("sample_news_*.json")):
        doc = load_json_file(file_path)
        graph_data = extract_graph(doc)
        output_path = OUTPUT_DIR / f"{file_path.stem}_graph.json"
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(graph_data, file, ensure_ascii=False, indent=2)
        print(f"[OK] 그래프 JSON 생성 완료: {output_path}")
