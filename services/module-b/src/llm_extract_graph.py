from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from jsonschema import validate

from company_whitelist import load_default_company_whitelist
from role_normalizer import normalize_graph_roles


BASE_DIR = Path(__file__).resolve().parent
MODULE_B_DIR = BASE_DIR.parent
ROOT_DIR = MODULE_B_DIR.parent.parent
ONTOLOGY_PATH = ROOT_DIR / "docs" / "ontology.md"
GRAPH_SCHEMA_PATH = ROOT_DIR / "schemas" / "graph_schema.json"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

load_dotenv()


def load_text_file(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


def load_json_file(file_path: Path) -> dict[str, Any]:
    return json.loads(file_path.read_text(encoding="utf-8"))


def build_extraction_prompt(doc: dict[str, Any]) -> str:
    ontology = load_text_file(ONTOLOGY_PATH)
    graph_schema = json.dumps(load_json_file(GRAPH_SCHEMA_PATH), ensure_ascii=False, indent=2)
    company_whitelist = load_default_company_whitelist()
    allowed_companies = company_whitelist.allowed_companies_for_doc(doc)
    allowed_company_text = "\n".join(
        f"- {company.company_name} ({company.stock_code}, {company.market})"
        for company in allowed_companies
    ) or "- No listed company from the whitelist was detected in this document."

    business_inference_rules = """
Business inference extraction rules:
- Entity.type may include Company, Person, Event, Industry, BusinessArea, and ProductService.
- Relation.type may include ACQUIRES, INVESTS_IN, APPOINTED_TO, AFFILIATED_WITH, BELONGS_TO, OPERATES_IN, PRODUCES, and PART_OF.
- For business_segments documents, extract specific BusinessArea entities when explicitly supported by text_blocks/content.
- For business_segments documents, extract ProductService entities for concrete products or services when explicitly supported by text_blocks/content.
- BusinessArea and ProductService names must be concise noun phrases, not full sentences.
- OPERATES_IN must use Company -> BusinessArea.
- PRODUCES must use Company -> ProductService.
- PART_OF must use BusinessArea -> Industry or ProductService -> BusinessArea.
- Use BELONGS_TO only for broad Company -> Industry links. Use OPERATES_IN/PRODUCES for business-segment details.
""".strip()

    return f"""
{business_inference_rules}

Listed-company whitelist rules:
- Only create Company entities for companies in the allowed listed-company set below.
- Do not create Company entities for unlisted companies, foreign companies, subsidiaries, public agencies, organizations, or generic institutions that are not in the allowed set.
- Do not create any relation if either endpoint would be an unlisted Company.
- When creating a Company entity, use the exact company_name from the allowed set as Company.name.
- For business_segments documents, fill Company.description with one concise Korean sentence based only on text_blocks/content.
- Company.description must summarize main business areas, products, or services in 120 Korean characters or less.
- Do not copy full text into Company.description. Omit description if the document does not provide clear business details.
- If the document mentions no allowed listed company, return the source_id with empty entities and relations.

Allowed listed companies detected for this document:
{allowed_company_text}

다음 금융/산업 문서에서 온톨로지 기준 엔티티와 관계를 추출해라.

반드시 지켜야 할 출력 조건:
- 출력은 JSON 객체 하나만 반환한다. 설명 문장이나 markdown을 붙이지 않는다.
- source_id는 입력 문서의 source_id를 그대로 사용한다.
- 스키마에 정의되지 않은 필드는 절대 추가하지 않는다.
- 엔티티 type은 Company, Person, Event, Industry 중 하나만 사용한다.
- 관계 type은 ACQUIRES, INVESTS_IN, APPOINTED_TO, AFFILIATED_WITH, BELONGS_TO 중 하나만 사용한다.
- 모든 relation.from/relation.to는 반드시 entities 배열에 존재하는 id여야 한다.
- 같은 id를 가진 엔티티를 중복 생성하지 않는다. 같은 대상을 한 번만 만들고 표기는 가장 공식적인 이름으로 통일한다.
- 관계의 evidence는 반드시 입력 문서에 실제로 있는 원문 문장 또는 원문에 가까운 단일 문장을 사용한다.
- Do not invent evidence source fields. Module B will attach evidence_source_id, evidence_source_type, evidence_source_url, and evidence_published_at after extraction.
- 텍스트 근거가 없는 엔티티/관계는 만들지 않는다.

엔티티 품질 규칙:
- Person.name에는 직책, 회사명, 수식어를 넣지 말고 사람 이름만 넣는다.
- Person.role에는 원문 직책 문자열을 넣는다. 예: "삼성전자 회장", "대표이사 사장", "사외이사".
  후처리에서 role_raw, role, role_label로 정규화하므로 role 값을 표준 코드로 직접 바꾸지 않는다.
- Company.name에는 가능한 공식 회사명을 넣고, id는 그 이름과 일관되게 만든다.
- Inc./Ltd./Corp.처럼 마침표 유무만 다른 회사는 같은 회사로 보고 하나의 엔티티만 만든다.
- Industry 엔티티를 relation.to로 사용할 경우 반드시 entities에도 같은 id의 Industry를 추가한다.

관계 품질 규칙:
- AFFILIATED_WITH/APPOINTED_TO는 Person -> Company 방향만 사용한다.
- ACQUIRES/INVESTS_IN은 Company -> Company 방향만 사용한다. 투자 주체가 연기금/기관이면 Company 타입의 기관 엔티티로 추가한다.
- BELONGS_TO는 Company -> Industry 방향만 사용한다.
- 회사명과 직책을 role 문자열 하나로 합치지 않는다. 회사는 Company 엔티티 및 관계로, 직책은 Person.role로 분리한다.
- 관계 endpoint를 확신할 수 없거나 빈 문자열이 될 경우 그 관계는 생성하지 않는다.
- Event 엔티티는 사건 자체를 설명할 때만 만들고, 관계 endpoint에 "Event" 같은 타입명 문자열을 넣지 않는다.

온톨로지:
{ontology}

그래프 JSON 스키마:
{graph_schema}

입력 문서:
{json.dumps(doc, ensure_ascii=False, indent=2)}
""".strip()


def extract_graph_with_openai(
    doc: dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
    resolved_model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not resolved_api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

    payload = {
        "model": resolved_model,
        "input": build_extraction_prompt(doc),
        "text": {
            "format": {
                "type": "json_object",
            }
        },
    }
    headers = {
        "Authorization": f"Bearer {resolved_api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()

    response_json = response.json()
    output_text = extract_output_text(response_json)
    graph_data = json.loads(output_text)
    graph_data = normalize_graph_roles(graph_data, load_default_company_whitelist(), doc)
    validate(instance=graph_data, schema=load_json_file(GRAPH_SCHEMA_PATH))
    return graph_data


def extract_output_text(response_json: dict[str, Any]) -> str:
    if response_json.get("output_text"):
        return response_json["output_text"]

    output_items = response_json.get("output", [])
    for item in output_items:
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                return text

    raise RuntimeError("OpenAI 응답에서 텍스트 출력을 찾지 못했습니다.")
