from __future__ import annotations

import re
from typing import Any


DEFAULT_COMPANY_HINTS = [
    "삼성전자",
    "SK하이닉스",
    "현대차",
    "LG에너지솔루션",
    "HD현대중공업",
    "삼성바이오로직스",
    "두산에너빌리티",
    "삼성전기",
    "SK스퀘어",
    "한화에어로스페이스",
]


def split_text_into_chunks(
    doc: dict[str, Any],
    max_chunk_length: int = 120,
) -> list[dict[str, Any]]:
    content = doc.get("content", "").strip()
    if not content:
        return []

    sentences = split_long_parts(split_sentences(content), max_chunk_length)
    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chunk_length:
            current_chunk = f"{current_chunk} {sentence}".strip()
            continue

        if current_chunk:
            chunks.append(current_chunk)
        current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return [
        {
            "doc_id": doc["source_id"],
            "chunk_id": f"{doc['source_id']}_chunk_{index}",
            "text": chunk_text,
            "title": doc.get("title", ""),
            "source": doc.get("source", ""),
            "published_at": doc.get("published_at", ""),
            "url": doc.get("url", ""),
            "chunk_index": index,
            "company_hint": extract_company_hints(doc, chunk_text),
        }
        for index, chunk_text in enumerate(chunks)
    ]


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?。？！])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def split_long_parts(parts: list[str], max_length: int) -> list[str]:
    results: list[str] = []
    for part in parts:
        if len(part) <= max_length:
            results.append(part)
            continue

        for start in range(0, len(part), max_length):
            piece = part[start : start + max_length].strip()
            if piece:
                results.append(piece)

    return results


def extract_company_hints(doc: dict[str, Any], text: str) -> list[str]:
    candidates = list(DEFAULT_COMPANY_HINTS)
    title = doc.get("title", "")

    for key in ["company_name", "corp_name"]:
        if doc.get(key):
            candidates.append(str(doc[key]))

    candidates.extend(str(value) for value in doc.get("mentioned_companies", []) if value)
    candidates.extend(
        re.findall(
            r"\b[A-Z][A-Za-z0-9&.\- ]{1,40}(?:Inc|Corp|Co|Ltd|Group)\b",
            f"{title} {text}",
        )
    )

    seen: set[str] = set()
    results: list[str] = []
    haystack = f"{title} {text}"

    for keyword in candidates:
        if keyword in haystack and keyword not in seen:
            seen.add(keyword)
            results.append(keyword)

    return results
