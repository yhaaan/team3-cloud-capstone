from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


REQUIRED_FIELDS = ["source_id", "title", "content", "source", "published_at", "url"]


def load_json_file(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def iter_input_documents(input_path: Path) -> list[dict[str, Any]]:
    if input_path.is_dir():
        documents: list[dict[str, Any]] = []
        for child in sorted(input_path.iterdir()):
            if child.suffix.lower() == ".json":
                documents.append(normalize_document(load_json_file(child), child))
            elif child.suffix.lower() == ".jsonl":
                documents.extend(load_jsonl_file(child))
        return documents

    if input_path.suffix.lower() == ".json":
        return [normalize_document(load_json_file(input_path), input_path)]

    if input_path.suffix.lower() == ".jsonl":
        return load_jsonl_file(input_path)

    raise ValueError(f"지원하지 않는 입력 형식입니다: {input_path}")


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
    missing_fields = [field for field in REQUIRED_FIELDS if not doc.get(field)]
    if missing_fields:
        location = f"{source_path}:{line_number}" if line_number else str(source_path)
        raise ValueError(f"필수 필드 누락 {missing_fields}: {location}")

    return {
        "source_id": str(doc["source_id"]),
        "title": str(doc["title"]),
        "content": str(doc["content"]),
        "source": str(doc["source"]),
        "published_at": str(doc["published_at"]),
        "url": str(doc["url"]),
    }


def write_json_file(output_path: Path, data: dict[str, Any]) -> None:
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
