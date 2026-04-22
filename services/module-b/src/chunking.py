from __future__ import annotations

import re
from typing import Any


DEFAULT_COMPANY_HINTS = [
    "카카오",
    "네이버",
    "삼성전자",
    "LG전자",
    "SK하이닉스",
    "현대자동차",
]


def split_text_into_chunks(
    doc: dict[str, Any],
    max_chunk_length: int = 120,
) -> list[dict[str, Any]]:
    """입력 문서를 문장 기반 청크로 분할한다."""

    content = doc.get("content", "").strip()
    if not content:
        return []

    sentences = split_sentences(content)
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
            "company_hint": extract_company_hints(doc.get("title", ""), chunk_text),
        }
        for index, chunk_text in enumerate(chunks)
    ]


def split_sentences(text: str) -> list[str]:
    """마침표, 물음표, 느낌표를 기준으로 문장을 분리한다."""

    normalized = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def extract_company_hints(title: str, text: str) -> list[str]:
    """제목과 본문에서 회사 후보명을 단순 추출한다."""

    candidates = list(DEFAULT_COMPANY_HINTS)
    candidates.extend(re.findall(r"[A-Z]사", f"{title} {text}"))

    seen: set[str] = set()
    results: list[str] = []
    haystack = f"{title} {text}"

    for keyword in candidates:
        if keyword in haystack and keyword not in seen:
            seen.add(keyword)
            results.append(keyword)

    return results


if __name__ == "__main__":
    sample_doc = {
        "source_id": "news_001",
        "title": "카카오, A사 인수 발표",
        "content": (
            "카카오는 2026년 3월 20일 A사 인수를 발표했다. "
            "이번 인수는 AI 사업 강화를 위한 전략적 결정이다. "
            "카카오는 신규 사업 확장을 추진할 계획이라고 밝혔다."
        ),
        "source": "mock_news",
        "published_at": "2026-03-20",
        "url": "https://example.com/news/001",
    }

    for chunk in split_text_into_chunks(sample_doc, max_chunk_length=80):
        print(chunk)
