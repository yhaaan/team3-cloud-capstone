from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from document_io import iter_input_documents
from load_chroma import (
    OpenAIEmbeddingFunction,
    build_client_and_collection,
    insert_doc_to_chroma_collection,
)
from load_neo4j import OUTPUT_DIR
from run_pipeline import MODULE_A_DATA_DIR, run_for_document


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Module B with Module A data and load graph results into Neo4j."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=MODULE_A_DATA_DIR,
        help="Module A data file or directory. Defaults to services/module-a/data.",
    )
    parser.add_argument(
        "--extractor",
        choices=["rule", "openai"],
        default="openai",
        help="Graph extraction mode. Defaults to openai.",
    )
    parser.add_argument(
        "--neo4j-uri",
        default=os.getenv("NEO4J_URI"),
        help="Neo4j Bolt URI.",
    )
    parser.add_argument(
        "--neo4j-user",
        default=os.getenv("NEO4J_USER", "neo4j"),
        help="Neo4j username.",
    )
    parser.add_argument(
        "--neo4j-password",
        default=os.getenv("NEO4J_PASSWORD"),
        help="Neo4j password.",
    )
    parser.add_argument(
        "--skip-chroma",
        action="store_true",
        help="Skip Chroma chunk insertion. Chroma is enabled by default.",
    )
    parser.add_argument(
        "--chroma-only",
        action="store_true",
        help="Only insert chunks into Chroma. Skip graph extraction and Neo4j loading.",
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not fall back to rule extraction when OpenAI extraction fails.",
    )
    parser.add_argument(
        "--min-relation-score",
        type=float,
        default=0.6,
        help="Minimum relation_relevance_score required for graph extraction and Neo4j loading.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N documents. Useful for smoke tests.",
    )
    parser.add_argument(
        "--start-from",
        default=None,
        help="Start processing from this source_id.",
    )
    parser.add_argument(
        "--start-after",
        default=None,
        help="Start processing after this source_id.",
    )
    parser.add_argument(
        "--force-graph",
        action="store_true",
        help="Regenerate graph JSON even when an output file already exists.",
    )
    return parser


def main() -> None:
    load_dotenv(override=True)
    args = build_argument_parser().parse_args()

    if not args.chroma_only and (not args.neo4j_uri or not args.neo4j_password):
        raise RuntimeError("Neo4j URI and password are required. Set NEO4J_URI and NEO4J_PASSWORD in .env or pass --neo4j-uri/--neo4j-password.")
    if args.chroma_only and args.skip_chroma:
        raise RuntimeError("--chroma-only cannot be used with --skip-chroma.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    documents = iter_input_documents(args.input)
    documents = slice_documents(
        documents,
        start_from=args.start_from,
        start_after=args.start_after,
    )
    if args.limit is not None:
        documents = documents[: args.limit]

    chroma_client = None
    chroma_collection = None
    if not args.skip_chroma:
        chroma_client, chroma_collection = build_client_and_collection()

    for doc in documents:
        if args.chroma_only:
            insert_doc_to_chroma_collection(chroma_collection, doc, source_name=doc["source_id"])
            continue

        run_for_document(
            doc=doc,
            extractor_mode=args.extractor,
            use_chroma=not args.skip_chroma,
            chroma_collection=chroma_collection,
            use_neo4j=True,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            allow_fallback=not args.no_fallback,
            min_relation_score=args.min_relation_score,
            force_graph=args.force_graph,
        )

    if chroma_collection is not None:
        chunk_count = chroma_collection.count()
        print(f"[OK] Chroma collection count: {chunk_count}")
        if chroma_client is not None:
            chroma_client.close()
            chroma_client = None

        verify_client, verify_collection = build_client_and_collection()
        query_embedding = OpenAIEmbeddingFunction()(["module b chroma validation"])[0]
        verify_collection.query(
            query_embeddings=[query_embedding],
            n_results=1,
        )
        verify_client.close()
        print("[OK] Chroma vector query validation passed")

    if args.chroma_only:
        print(f"[OK] Processed and loaded {len(documents)} documents into Chroma")
    else:
        print(f"[OK] Processed and loaded {len(documents)} documents into Neo4j")


def slice_documents(
    documents: list[dict[str, str]],
    start_from: str | None = None,
    start_after: str | None = None,
) -> list[dict[str, str]]:
    if start_from and start_after:
        raise RuntimeError("--start-from and --start-after cannot be used together.")
    if not start_from and not start_after:
        return documents

    source_ids = [doc["source_id"] for doc in documents]
    marker = start_from or start_after
    if marker not in source_ids:
        raise RuntimeError(f"source_id not found: {marker}")

    index = source_ids.index(marker)
    if start_after:
        index += 1
    return documents[index:]


if __name__ == "__main__":
    main()

