from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import validate


REQUIRED_FIELDS = [
    "source_id",
    "document_type",
    "title",
    "content",
    "source",
    "published_at",
    "url",
    "metadata",
]
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent.parent
INPUT_SCHEMA_PATH = ROOT_DIR / "schemas" / "input_document_schema.json"


def load_json_file(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_input_schema() -> dict[str, Any]:
    return load_json_file(INPUT_SCHEMA_PATH)


def iter_input_documents(input_path: Path) -> list[dict[str, Any]]:
    if input_path.is_dir():
        documents: list[dict[str, Any]] = []
        for child in sorted(input_path.rglob("*")):
            if child.suffix.lower() == ".json":
                documents.append(normalize_document(load_json_file(child), child))
            elif child.suffix.lower() == ".jsonl":
                documents.extend(load_jsonl_file(child))
        return documents

    if input_path.suffix.lower() == ".json":
        return [normalize_document(load_json_file(input_path), input_path)]

    if input_path.suffix.lower() == ".jsonl":
        return load_jsonl_file(input_path)

    raise ValueError(f"Unsupported input format: {input_path}")


def load_jsonl_file(file_path: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []

    with file_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            doc = json.loads(stripped)
            documents.append(normalize_document(doc, file_path, line_number))

    return documents


def normalize_document(
    doc: dict[str, Any],
    source_path: Path,
    line_number: int | None = None,
) -> dict[str, Any]:
    if has_required_fields(doc):
        normalized = normalize_module_b_document(doc)
    elif is_module_a_news_document(doc):
        normalized = normalize_module_a_news_document(doc, source_path)
    elif is_module_a_dart_document(doc):
        normalized = normalize_module_a_dart_document(doc, source_path)
    else:
        try:
            normalized = normalize_module_b_document(doc)
        except ValueError as exc:
            location = f"{source_path}:{line_number}" if line_number else str(source_path)
            raise ValueError(f"{exc}: {location}") from exc

    validate(instance=normalized, schema=load_input_schema())
    return normalized


def has_required_fields(doc: dict[str, Any]) -> bool:
    return all(field in doc and doc.get(field) not in [None, ""] for field in REQUIRED_FIELDS)


def normalize_module_b_document(doc: dict[str, Any]) -> dict[str, Any]:
    base_required_fields = ["source_id", "title", "content", "source", "published_at", "url"]
    missing_fields = [field for field in base_required_fields if not doc.get(field)]
    if missing_fields:
        raise ValueError(f"Missing required fields {missing_fields}")

    normalized = {
        "source_id": str(doc["source_id"]),
        "document_type": str(doc.get("document_type") or "unknown"),
        "title": str(doc["title"]),
        "content": str(doc["content"]),
        "source": str(doc["source"]),
        "published_at": str(doc["published_at"]),
        "url": str(doc["url"]),
        "company_name": doc.get("company_name"),
        "stock_code": doc.get("stock_code"),
        "corp_code": doc.get("corp_code"),
        "metadata": dict(doc.get("metadata") or {}),
    }
    normalized.update(
        {key: value for key, value in doc.items() if key not in normalized and key != "metadata"}
    )
    return normalized


def is_module_a_news_document(doc: dict[str, Any]) -> bool:
    return bool(
        doc.get("doc_id")
        and (
            "body_text" in doc
            or "sentences" in doc
            or "originallink" in doc
            or "naver_link" in doc
        )
    )


def normalize_module_a_news_document(doc: dict[str, Any], source_path: Path) -> dict[str, Any]:
    content = str(
        doc.get("body_text")
        or " ".join(doc.get("sentences", []))
        or doc.get("title")
        or doc["doc_id"]
    ).strip()
    url = first_non_empty(doc, "originallink", "naver_link")

    return {
        "source_id": str(doc["doc_id"]),
        "document_type": "news",
        "title": str(doc.get("title") or doc["doc_id"]),
        "content": content,
        "source": str(doc.get("source") or "module_a_news"),
        "published_at": str(doc.get("published_at") or doc.get("cleaned_at") or "unknown"),
        "url": url or source_path.as_posix(),
        "company_name": doc.get("company_name"),
        "stock_code": doc.get("stock_code"),
        "module_a_type": "news",
        "mentioned_companies": doc.get("mentioned_companies", []),
        "mentioned_people": doc.get("mentioned_people", []),
        "relation_keywords_detected": doc.get("relation_keywords_detected", []),
        "relation_relevance_score": doc.get("relation_relevance_score"),
        "is_relation_candidate": doc.get("is_relation_candidate"),
        "metadata": {
            "module_a_path": source_path.as_posix(),
            "press": doc.get("press"),
            "originallink": doc.get("originallink"),
            "naver_link": doc.get("naver_link"),
            "sentences": doc.get("sentences", []),
            "mentioned_companies": doc.get("mentioned_companies", []),
            "mentioned_people": doc.get("mentioned_people", []),
            "relation_keywords_detected": doc.get("relation_keywords_detected", []),
            "relation_relevance_score": doc.get("relation_relevance_score"),
            "is_relation_candidate": doc.get("is_relation_candidate"),
            "company_relevance_score": doc.get("company_relevance_score"),
            "is_company_relevant": doc.get("is_company_relevant"),
            "cleaned_at": doc.get("cleaned_at"),
        },
    }


def is_module_a_dart_document(doc: dict[str, Any]) -> bool:
    return bool(doc.get("doc_id") and doc.get("source") == "dart")


def normalize_module_a_dart_document(doc: dict[str, Any], source_path: Path) -> dict[str, Any]:
    rcept_no = str(doc.get("rcept_no") or "").strip()
    dataset_label = str(doc.get("dataset_label") or doc.get("dataset") or "DART disclosure")
    company_name = str(doc.get("company_name") or doc.get("corp_name") or "").strip()
    title = " ".join(part for part in [company_name, dataset_label] if part).strip()

    return {
        "source_id": str(doc["doc_id"]),
        "document_type": "dart",
        "title": title or str(doc["doc_id"]),
        "content": build_dart_content(doc),
        "source": "dart",
        "published_at": str(
            doc.get("rcept_dt") or doc.get("generated_at") or doc.get("bsns_year") or "unknown"
        ),
        "url": build_dart_url(rcept_no) or source_path.as_posix(),
        "company_name": doc.get("company_name"),
        "stock_code": doc.get("stock_code"),
        "corp_code": doc.get("corp_code"),
        "dataset": doc.get("dataset"),
        "dataset_label": doc.get("dataset_label"),
        "rcept_no": doc.get("rcept_no"),
        "module_a_type": "dart",
        "mentioned_entities": doc.get("mentioned_entities", []),
        "relation_keywords_detected": doc.get("relation_keywords_detected", []),
        "relation_relevance_score": doc.get("relation_relevance_score"),
        "is_relation_candidate": doc.get("is_relation_candidate"),
        "metadata": {
            "module_a_path": source_path.as_posix(),
            "dataset": doc.get("dataset"),
            "dataset_label": doc.get("dataset_label"),
            "bsns_year": doc.get("bsns_year"),
            "reprt_code": doc.get("reprt_code"),
            "rcept_no": doc.get("rcept_no"),
            "record_count": doc.get("record_count"),
            "meaningful_record_count": doc.get("meaningful_record_count"),
            "normalized_records": doc.get("normalized_records"),
            "text_blocks": doc.get("text_blocks"),
            "mentioned_entities": doc.get("mentioned_entities", []),
            "relation_keywords_detected": doc.get("relation_keywords_detected", []),
            "relation_relevance_score": doc.get("relation_relevance_score"),
            "is_relation_candidate": doc.get("is_relation_candidate"),
            "raw_file_path": doc.get("raw_file_path"),
            "generated_at": doc.get("generated_at"),
        },
    }


def build_dart_content(doc: dict[str, Any]) -> str:
    text_blocks = [str(block).strip() for block in doc.get("text_blocks", []) if str(block).strip()]
    if text_blocks:
        return "\n".join(text_blocks)

    records = doc.get("normalized_records", [])
    if records:
        return json.dumps(records, ensure_ascii=False)

    summary_parts = [
        doc.get("company_name"),
        doc.get("dataset_label") or doc.get("dataset"),
        doc.get("rcept_no"),
        doc.get("bsns_year"),
    ]
    return " ".join(str(part) for part in summary_parts if part) or str(doc["doc_id"])


def build_dart_url(rcept_no: str) -> str:
    if not rcept_no:
        return ""
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def first_non_empty(doc: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = doc.get(key)
        if value:
            return str(value)
    return ""


def write_json_file(output_path: Path, data: dict[str, Any]) -> None:
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
