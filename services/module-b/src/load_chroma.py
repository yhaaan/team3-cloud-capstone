from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import chromadb
import numpy as np
import requests
from dotenv import load_dotenv
from jsonschema import validate

from chunking import split_text_into_chunks
from document_io import iter_input_documents, load_json_file, normalize_document


BASE_DIR = Path(__file__).resolve().parent
MODULE_B_DIR = BASE_DIR.parent
ROOT_DIR = MODULE_B_DIR.parent.parent
MODULE_A_DATA_DIR = ROOT_DIR / "services" / "module-a" / "data"
CHROMA_DIR = MODULE_B_DIR / "local_db" / "chroma"
CHUNK_SCHEMA_PATH = ROOT_DIR / "schemas" / "chunk_schema.json"
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
CHROMA_UPSERT_BATCH_SIZE = 100

load_dotenv()


class OpenAIEmbeddingFunction:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int = 60,
        batch_size: int = 64,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        self.timeout = timeout
        self.batch_size = batch_size

        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for Chroma OpenAI embeddings.")

    def __call__(self, input: list[str]) -> list[np.ndarray]:
        embeddings: list[np.ndarray] = []
        for start in range(0, len(input), self.batch_size):
            embeddings.extend(self._embed_batch(input[start : start + self.batch_size]))
        return embeddings

    def _embed_batch(self, input_batch: list[str]) -> list[np.ndarray]:
        response = requests.post(
            OPENAI_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": input_batch},
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(
                f"OpenAI embeddings request failed ({response.status_code}): {response.text}"
            )
        response_json = response.json()
        ordered = sorted(response_json["data"], key=lambda item: item["index"])
        return [np.array(item["embedding"], dtype=np.float32) for item in ordered]

    @staticmethod
    def name() -> str:
        return "openai_text_embedding_3_small"

    def get_config(self) -> dict[str, Any]:
        return {"model": self.model}

    @staticmethod
    def default_space() -> str:
        return "cosine"

    @staticmethod
    def supported_spaces() -> list[str]:
        return ["cosine", "l2", "ip"]


def load_chunk_schema() -> dict[str, Any]:
    return load_json_file(CHUNK_SCHEMA_PATH)


def build_collection():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedding_function = OpenAIEmbeddingFunction()

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
        print(f"[SKIP] No chunks: {source_name}")
        return 0

    collection = build_collection()
    for start in range(0, len(documents), CHROMA_UPSERT_BATCH_SIZE):
        end = start + CHROMA_UPSERT_BATCH_SIZE
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
    print(f"[OK] {source_name} -> {len(documents)} chunks inserted")
    return len(documents)


def insert_document_to_chroma(file_path: Path) -> int:
    doc = normalize_document(load_json_file(file_path), file_path)
    return insert_doc_to_chroma(doc, source_name=file_path.name)


def search_example(query_text: str) -> None:
    collection = build_collection()
    results = collection.query(query_texts=[query_text], n_results=3)

    print("\n=== Search results ===")
    for index, document in enumerate(results["documents"][0]):
        print(f"[{index}] {document}")
        print("metadata:", results["metadatas"][0][index])
        print()


if __name__ == "__main__":
    for document in iter_input_documents(MODULE_A_DATA_DIR):
        insert_doc_to_chroma(document, source_name=document["source_id"])

    search_example("company relationship investment")
