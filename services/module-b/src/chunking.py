from __future__ import annotations

from typing import Any
import re


def split_text_into_chunks(
    doc: dict[str, Any],
    max_chunk_length: int = 120,
) -> list[dict[str, Any]]:
    """
    입력 문서를 청크 단위로 분할한다.
    현재는 문장 단위로 자른 뒤, 최대 길이를 넘지 않도록 묶는 단순 버전이다.
    """

    content = doc.get("content", "").strip()
    if not content:
        return []

    sentences = split_sentences(content)

    chunks: list[str] = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current_chunk) + len(sentence) + 1 <= max_chunk_length:
            current_chunk = f"{current_chunk} {sentence}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    chunk_docs: list[dict[str, Any]] = []
    for index, chunk_text in enumerate(chunks):
        chunk_docs.append(
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
        )

    return chunk_docs


def split_sentences(text: str) -> list[str]:
    """
    아주 단순한 문장 분리 함수
    마침표, 물음표, 느낌표 기준으로 분리
    """
    parts = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", text)
    return [part.strip() for part in parts if part.strip()]


def extract_company_hints(title: str, text: str) -> list[str]:
    """
    임시 버전:
    title과 text에서 자주 등장하는 회사 후보를 매우 단순하게 추출한다.
    나중에는 NER 또는 룰 기반으로 대체 가능
    """
    candidates = []

    for keyword in ["카카오", "네이버", "삼성전자", "A사", "B사", "C사"]:
        if keyword in title or keyword in text:
            candidates.append(keyword)

    return candidates


if __name__ == "__main__":
    sample_doc = {
        "source_id": "news_001",
        "title": "카카오, A사 인수 발표",
        "content": "카카오는 2026년 3월 20일 A사 인수를 발표했다. 이번 인수는 AI 사업 강화를 위한 전략적 결정이다. 카카오는 신규 사업 확장을 추진할 계획이라고 밝혔다.",
        "source": "mock_news",
        "published_at": "2026-03-20",
        "url": "https://example.com/news/001",
    }

    results = split_text_into_chunks(sample_doc, max_chunk_length=80)
    for chunk in results:
        print(chunk)