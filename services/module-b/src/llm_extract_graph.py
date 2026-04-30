from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from jsonschema import validate


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

    return f"""
다음 금융 뉴스 문서에서 온톨로지 기준 엔티티와 관계를 추출해라.

반드시 지켜야 할 조건:
- 출력은 JSON 객체 하나만 반환한다.
- 스키마에 정의되지 않은 필드는 추가하지 않는다.
- 텍스트 근거가 없는 엔티티/관계는 만들지 않는다.
- 관계의 evidence는 반드시 원문 문장을 사용한다.
- 관계 type은 ACQUIRES, INVESTS_IN, APPOINTED_TO, AFFILIATED_WITH, BELONGS_TO 중 하나만 사용한다.
- 엔티티 type은 Company, Person, Event, Industry 중 하나만 사용한다.
- source_id는 입력 문서의 source_id를 그대로 사용한다.

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
