from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import validate

from chunking import split_sentences
from company_whitelist import load_default_company_whitelist
from role_normalizer import normalize_graph_roles


BASE_DIR = Path(__file__).resolve().parent
MODULE_B_DIR = BASE_DIR.parent
ROOT_DIR = MODULE_B_DIR.parent.parent
GRAPH_SCHEMA_PATH = ROOT_DIR / "schemas" / "graph_schema.json"

INDUSTRY_KEYWORDS = [
    "HBM",
    "cloud",
    "battery",
    "shipbuilding",
    "construction",
    "logistics",
    "insurance",
    "platform",
    "semiconductor",
    "bio",
    "energy",
    "AI",
]

PRODUCT_SERVICE_KEYWORDS = [
    "DRAM",
    "OLED",
    "EV battery",
    "LNG carrier",
    "cloud service",
    "securities brokerage",
    "smartphone",
    "display",
    "memory",
]

RELATION_KEYWORDS = {
    "ACQUIRES": ["acquire", "acquisition", "merger", "인수", "합병"],
    "INVESTS_IN": ["invest", "investment", "투자", "출자"],
    "APPOINTED_TO": ["appoint", "appointed", "선임", "임명"],
    "AFFILIATED_WITH": ["executive", "director", "CEO", "COO", "임원", "대표", "사장", "부사장"],
}


def load_json_file(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize_name(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", "_", value.strip()).strip("_").lower()
    return normalized or "unknown"


def build_entity_id(entity_type: str, name: str) -> str:
    prefixes = {
        "product_service": "product_service",
    }
    prefix = prefixes.get(entity_type.lower(), entity_type.lower())
    return f"{prefix}_{normalize_name(name)}"


def extract_graph(doc: dict[str, Any]) -> dict[str, Any]:
    title = doc.get("title", "")
    content = doc.get("content", "")
    source_id = doc.get("source_id", "unknown")
    company_whitelist = load_default_company_whitelist()

    companies = [
        company
        for company in collect_companies(doc, title, content)
        if company_whitelist.is_allowed_name(company)
    ]
    people = collect_people(doc, content)
    industries = collect_industries(doc, content)
    product_services = collect_product_services(doc, content)

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
                "role": person.get("role", ""),
            }
        )

    for industry in industries:
        entities.append(
            {"id": build_entity_id("industry", industry), "type": "Industry", "name": industry}
        )

    for product_service in product_services:
        entities.append(
            {
                "id": build_entity_id("product_service", product_service),
                "type": "ProductService",
                "name": product_service,
            }
        )

    if len(companies) >= 2 and has_relation_keyword(content, "ACQUIRES"):
        relations.append(
            build_relation("ACQUIRES", "company", companies[0], "company", companies[1], content)
        )

    if len(companies) >= 2 and has_relation_keyword(content, "INVESTS_IN"):
        relations.append(
            build_relation("INVESTS_IN", "company", companies[0], "company", companies[1], content)
        )

    if companies and industries:
        for industry in industries:
            relations.append(
                build_relation("BELONGS_TO", "company", companies[0], "industry", industry, content)
            )

    if companies and product_services:
        for product_service in product_services:
            relations.append(
                build_relation(
                    "PRODUCES",
                    "company",
                    companies[0],
                    "product_service",
                    product_service,
                    content,
                )
            )

    if product_services and industries:
        for product_service in product_services:
            relations.append(
                build_relation(
                    "PART_OF",
                    "product_service",
                    product_service,
                    "industry",
                    industries[0],
                    content,
                )
            )

    if companies and people and has_relation_keyword(content, "APPOINTED_TO"):
        relations.append(
            build_relation("APPOINTED_TO", "person", people[0]["name"], "company", companies[0], content)
        )

    if companies and people and has_relation_keyword(content, "AFFILIATED_WITH"):
        relations.append(
            build_relation(
                "AFFILIATED_WITH",
                "person",
                people[0]["name"],
                "company",
                companies[0],
                content,
            )
        )

    graph = {
        "source_id": source_id,
        "entities": deduplicate_entities(entities),
        "relations": [relation for relation in relations if relation["evidence"]],
    }
    graph = normalize_graph_roles(graph, company_whitelist, doc)
    validate(instance=graph, schema=load_json_file(GRAPH_SCHEMA_PATH))
    return graph


def collect_companies(doc: dict[str, Any], title: str, content: str) -> list[str]:
    companies: list[str] = []

    for key in ["company_name", "corp_name"]:
        if doc.get(key):
            companies.append(str(doc[key]))

    companies.extend(str(value) for value in doc.get("mentioned_companies", []) if value)
    companies.extend(str(value) for value in doc.get("mentioned_entities", []) if value)
    companies.extend(re.findall(r"\b[A-Z][A-Za-z0-9&.\- ]{1,40}(?:Inc|Corp|Co|Ltd|Group)\b", title))
    companies.extend(re.findall(r"\b[A-Z][A-Za-z0-9&.\- ]{1,40}(?:Inc|Corp|Co|Ltd|Group)\b", content))

    return deduplicate_strings(companies)


def collect_people(doc: dict[str, Any], content: str) -> list[dict[str, str]]:
    people: list[dict[str, str]] = []

    for value in doc.get("mentioned_people", []):
        if value:
            people.append({"name": str(value), "role": ""})

    for match in re.finditer(r"([A-Z][a-z]+ [A-Z][a-z]+).{0,30}(CEO|COO|CFO|director|executive)", content):
        people.append({"name": match.group(1), "role": match.group(2)})

    return deduplicate_people(people)


def collect_industries(doc: dict[str, Any], content: str) -> list[str]:
    industries = ["AI", "cloud", "semiconductor", "battery", "bio", "shipbuilding", "energy", "IT"]
    if doc.get("dataset") == "business_segments":
        industries = deduplicate_strings([*industries, *INDUSTRY_KEYWORDS])
    lower_content = content.lower()
    return [industry for industry in industries if industry.lower() in lower_content]


def collect_product_services(doc: dict[str, Any], content: str) -> list[str]:
    if doc.get("dataset") != "business_segments":
        return []

    lower_content = content.lower()
    return [
        keyword
        for keyword in PRODUCT_SERVICE_KEYWORDS
        if keyword.lower() in lower_content
    ]


def build_relation(
    relation_type: str,
    from_type: str,
    from_name: str,
    to_type: str,
    to_name: str,
    content: str,
) -> dict[str, str]:
    return {
        "type": relation_type,
        "from": build_entity_id(from_type, from_name),
        "to": build_entity_id(to_type, to_name),
        "evidence": find_evidence_sentence(content, RELATION_KEYWORDS.get(relation_type, [to_name])),
    }


def find_evidence_sentence(content: str, keywords: list[str]) -> str:
    for sentence in split_sentences(content):
        lowered = sentence.lower()
        if any(keyword.lower() in lowered for keyword in keywords):
            return sentence
    return split_sentences(content)[0] if content.strip() else ""


def has_relation_keyword(content: str, relation_type: str) -> bool:
    lowered = content.lower()
    return any(keyword.lower() in lowered for keyword in RELATION_KEYWORDS[relation_type])


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
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            results.append(cleaned)
    return results


def deduplicate_people(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    results: list[dict[str, str]] = []
    for value in values:
        key = (value["name"], value.get("role", ""))
        if key not in seen:
            seen.add(key)
            results.append(value)
    return results
