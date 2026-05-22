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
- Extract specific BusinessArea entities when explicitly supported by text_blocks/content, normalized_records, or content.
- Extract ProductService entities for concrete products or services when explicitly supported by text_blocks/content, normalized_records, or content.
- BusinessArea and ProductService names must be concise noun phrases, not full sentences.
- OPERATES_IN must use Company -> BusinessArea.
- PRODUCES must use Company -> ProductService.
- PART_OF must use BusinessArea -> Industry or ProductService -> BusinessArea.
- Use BELONGS_TO only for broad Company -> Industry links. Use OPERATES_IN/PRODUCES for business-segment details.
- Prefer creating useful industry discovery paths:
  Company -> BusinessArea -> Industry
  Company -> ProductService -> BusinessArea -> Industry
  Company -> Industry when only broad industry evidence exists.
""".strip()

    authoritative_schema_rules = """
Authoritative schema priority:
- The JSON schema and Business inference extraction rules above are authoritative.
- If any later natural-language instruction conflicts with the schema, follow the schema.
- You may create BusinessArea and ProductService entities when evidence exists.
- You may create OPERATES_IN, PRODUCES, and PART_OF relations when evidence exists.
- For industry discovery, prefer extracting paths that connect Company -> BusinessArea/ProductService -> Industry, or Company -> Industry when only broad evidence exists.
""".strip()

    output_rules = """
Output rules:
- Return exactly one JSON object. Do not include explanations or markdown.
- Use the input document source_id as source_id.
- Do not add fields that are not defined in the graph schema.
- Every relation.from and relation.to must reference an id in the entities array.
- Do not create duplicate entities with the same id. Use the most official name available.
- Every relation.evidence must be a source sentence or a close single-sentence excerpt from the input document.
- Do not invent evidence source fields. Module B attaches evidence_source_id, evidence_source_type, evidence_source_url, and evidence_published_at after extraction.
- Do not create entities or relations without textual evidence.
""".strip()

    entity_rules = """
Entity rules:
- Company.name must use the exact company_name from the allowed listed-company set when it represents a listed company.
- Company.id should be consistent with the company name; Module B will canonicalize listed companies by stock_code.
- Create Person entities only for DART executive_status documents. Do not create Person entities from news documents or non-executive DART documents.
- Person.name must contain only the person's name, not titles, company names, or modifiers.
- Person.role should contain the raw title string from the source text, not a standardized role code.
- For DART executive_status records, preserve birth_ym, gender, main_career, executive_type, full_time_status, responsibility, tenure, tenure_end_on, and major_shareholder_relation when present in the input.
- For DART executive_status records, use name plus birth_ym as the stable person identity when birth_ym is available.
- Industry is a broad sector or market category, such as semiconductor, battery, cloud, shipbuilding, insurance, construction, bio, energy, AI, or platform.
- BusinessArea is a company's business segment or operating area, such as memory, foundry, financial services, shipbuilding, construction, insurance, logistics, cloud, or platform business.
- ProductService is a concrete product, service, or offering, such as DRAM, HBM, OLED, EV battery, LNG carrier, brokerage service, cloud service, smartphone, or display panel.
- Industry, BusinessArea, and ProductService names must be short noun phrases.
- If a relation uses an Industry, BusinessArea, or ProductService endpoint, the endpoint entity must also appear in entities.
""".strip()

    relation_rules = """
Relation rules:
- ACQUIRES and INVESTS_IN are Company -> Company only.
- APPOINTED_TO and AFFILIATED_WITH are Person -> Company only.
- BELONGS_TO is Company -> Industry only and should be used for broad industry classification.
- OPERATES_IN is Company -> BusinessArea only.
- PRODUCES is Company -> ProductService only.
- PART_OF is BusinessArea -> Industry or ProductService -> BusinessArea only.
- Do not combine company names and titles into a role string. Use Company entities and relations for companies, and Person.role for titles.
- Do not create a relation if either endpoint is uncertain or empty.
- Create Event entities only when the event itself is important; never use a literal type name like "Event" as a relation endpoint.
""".strip()

    return f"""
{business_inference_rules}

Listed-company whitelist rules:
- Only create Company entities for companies in the allowed listed-company set below.
- The allowed listed-company set already excludes whitelist rows without corp_code.
- Do not create Company entities for unlisted companies, foreign companies, subsidiaries, public agencies, organizations, or generic institutions that are not in the allowed set.
- Do not create any relation if either endpoint would be an unlisted Company.
- When creating a Company entity, use the exact company_name from the allowed set as Company.name.
- For business_segments documents, fill Company.description with one concise Korean sentence based only on text_blocks/content.
- Company.description must summarize main business areas, products, or services in 120 Korean characters or less.
- Do not copy full text into Company.description. Omit description if the document does not provide clear business details.
- If the document mentions no allowed listed company, return the source_id with empty entities and relations.

Allowed listed companies detected for this document:
{allowed_company_text}

{output_rules}

{entity_rules}

{relation_rules}

Ontology:
{ontology}

{authoritative_schema_rules}

Graph JSON schema:
{graph_schema}

Input document:
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
