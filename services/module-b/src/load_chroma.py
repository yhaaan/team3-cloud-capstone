from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from chunking import split_text_into_chunks


BASE_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = BASE_DIR.parent / "tests" / "fixtures"
CHROMA_DIR = BASE_DIR.parent / "local_db" / "chroma"


def load_json_file(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_collection():
    """
    로컬 디스크에 저장되는 Chroma 컬렉션 생성
    """
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    collection = client.get_or_create_collection(
        name="module_b_chunks",
        embedding_function=embedding_function,
    )
    return collection


def insert_document_to_chroma(file_path: Path) -> None:
    doc = load_json_file(file_path)
    chunks = split_text_into_chunks(doc)

    if not chunks:
        print(f"[SKIP] 청크가 없습니다: {file_path.name}")
        return

    collection = build_collection()

    ids = []
    documents = []
    metadatas = []

    for chunk in chunks:
        ids.append(chunk["chunk_id"])
        documents.append(chunk["text"])
        metadatas.append(
            {
                "doc_id": chunk["doc_id"],
                "title": chunk["title"],
                "source": chunk["source"],
                "published_at": chunk["published_at"],
                "url": chunk["url"],
                "chunk_index": chunk["chunk_index"],
                "company_hint": ", ".join(chunk.get("company_hint", [])),
            }
        )

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    print(f"[OK] {file_path.name} -> {len(chunks)}개 청크 저장 완료")


def search_example(query_text: str) -> None:
    collection = build_collection()

    results = collection.query(
        query_texts=[query_text],
        n_results=3,
    )

    print("\n=== 검색 결과 ===")
    for i, doc in enumerate(results["documents"][0]):
        print(f"[{i}] {doc}")
        print("metadata:", results["metadatas"][0][i])
        print()


if __name__ == "__main__":
    for file_name in ["sample_news_01.json", "sample_news_02.json", "sample_news_03.json"]:
        insert_document_to_chroma(FIXTURE_DIR / file_name)

    search_example("카카오 인수 AI")