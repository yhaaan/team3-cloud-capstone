from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions
from jsonschema import validate

from chunking import split_text_into_chunks
from document_io import load_json_file


BASE_DIR = Path(__file__).resolve().parent
MODULE_B_DIR = BASE_DIR.parent
ROOT_DIR = MODULE_B_DIR.parent.parent
TEST_DATA_DIR = MODULE_B_DIR / "tests"
CHROMA_DIR = MODULE_B_DIR / "local_db" / "chroma"
CHUNK_SCHEMA_PATH = ROOT_DIR / "schemas" / "chunk_schema.json"

def load_chunk_schema() -> dict[str, Any]:
    return load_json_file(CHUNK_SCHEMA_PATH)


def build_collection():
    """로컬 디스크에 저장되는 Chroma 컬렉션을 생성한다."""

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    return client.get_or_create_collection(
        name="module_b_chunks",
        embedding_function=embedding_function,
    )


def build_chunk_payloads(doc: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    chunk_schema = load_chunk_schema()
    chunks = split_text_into_chunks(doc)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for chunk in chunks:
        validate(instance=chunk, schema=chunk_schema)
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

    return ids, documents, metadatas


def insert_doc_to_chroma(doc: dict[str, Any], source_name: str = "inline_doc") -> int:
    ids, documents, metadatas = build_chunk_payloads(doc)
    if not documents:
        print(f"[SKIP] 청크가 없습니다: {source_name}")
        return 0

    collection = build_collection()
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"[OK] {source_name} -> {len(documents)}개 청크 저장 완료")
    return len(documents)


def insert_document_to_chroma(file_path: Path) -> int:
    doc = load_json_file(file_path)
    return insert_doc_to_chroma(doc, source_name=file_path.name)


def search_example(query_text: str) -> None:
    collection = build_collection()
    results = collection.query(query_texts=[query_text], n_results=3)

    print("\n=== 검색 결과 ===")
    for index, document in enumerate(results["documents"][0]):
        print(f"[{index}] {document}")
        print("metadata:", results["metadatas"][0][index])
        print()


if __name__ == "__main__":
    for file_path in sorted(TEST_DATA_DIR.glob("sample_news_*.json")):
        insert_document_to_chroma(file_path)

    search_example("카카오 인수 AI")
