from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from log_utils import log_with_timestamp

from document_io import iter_input_documents, write_json_file
from ftc_affiliates import DEFAULT_FTC_AFFILIATES_PATH, build_ftc_affiliates_graph
from graph_pipeline import extract_graph
from load_chroma import (
    CHROMA_DIR,
    OpenAIEmbeddingFunction,
    build_client_and_collection,
    insert_doc_to_chroma_collection,
)
from load_neo4j import OUTPUT_DIR, load_graph_json, load_graphs_to_neo4j_batch
from run_to_neo4j import filter_documents_by_dataset, slice_documents


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent.parent
MODULE_A_DATA_DIR = ROOT_DIR / "services" / "module-a" / "data"
FAILURE_LOG_PATH = OUTPUT_DIR / "rebuild_failures.jsonl"


def main() -> None:
    load_dotenv(override=True)
    args = build_argument_parser().parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.stage in {"all", "reset"}:
        reset_derived_state(
            reset_outputs=args.reset_outputs,
            reset_chroma=args.reset_chroma,
            reset_neo4j=args.reset_neo4j,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
        )

    documents = load_selected_documents(args)

    if args.stage in {"all", "extract"}:
        extract_graphs_parallel(
            documents=documents,
            workers=args.workers,
            extractor_mode=args.extractor,
            allow_fallback=not args.no_fallback,
            min_relation_score=args.min_relation_score,
            force=args.force_graph,
        )

    if args.stage in {"all", "chroma"}:
        rebuild_chroma(documents)

    if args.stage in {"all", "neo4j"}:
        load_outputs_to_neo4j_batch(
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            batch_size=args.batch_size,
        )

    if args.stage in {"all", "ftc"}:
        load_ftc_to_neo4j_batch(
            ftc_input=args.ftc_input,
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            batch_size=args.batch_size,
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild Module B derived stores with parallel graph extraction.")
    parser.add_argument("--input", type=Path, default=MODULE_A_DATA_DIR)
    parser.add_argument(
        "--stage",
        choices=["all", "reset", "extract", "chroma", "neo4j", "ftc"],
        default="all",
        help="Rebuild stage to run. Defaults to all.",
    )
    parser.add_argument("--extractor", choices=["rule", "openai"], default="openai")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--min-relation-score", type=float, default=0.6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--datasets", nargs="+", default=None)
    parser.add_argument("--start-from", default=None)
    parser.add_argument("--start-after", default=None)
    parser.add_argument("--force-graph", action="store_true")
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--reset-outputs", action="store_true", help="Delete Module B graph output files before rebuild.")
    parser.add_argument("--reset-chroma", action="store_true", help="Delete Module B Chroma sqlite directory before rebuild.")
    parser.add_argument("--reset-neo4j", action="store_true", help="Delete existing (:Entity) graph data in Neo4j before rebuild.")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--ftc-input", type=Path, default=DEFAULT_FTC_AFFILIATES_PATH)
    return parser


def load_selected_documents(args: argparse.Namespace) -> list[dict[str, Any]]:
    documents = iter_input_documents(args.input)
    documents = filter_documents_by_dataset(documents, args.datasets)
    documents = slice_documents(documents, args.start_from, args.start_after)
    if args.limit is not None:
        documents = documents[: args.limit]
    return documents


def reset_derived_state(
    reset_outputs: bool,
    reset_chroma: bool,
    reset_neo4j: bool,
    neo4j_uri: str | None,
    neo4j_user: str | None,
    neo4j_password: str | None,
) -> None:
    if reset_outputs:
        clear_output_files()
    if reset_chroma:
        clear_chroma_dir()
    if reset_neo4j:
        clear_neo4j_entities(neo4j_uri, neo4j_user, neo4j_password)


def clear_output_files() -> None:
    removed = 0
    for pattern in ("*_graph.json", "*_graph.cypher.txt", "ftc_affiliates_*.cypher.txt", "rebuild_failures.jsonl"):
        for file_path in OUTPUT_DIR.glob(pattern):
            file_path.unlink()
            removed += 1
    log_with_timestamp(f"[OK] Removed {removed} Module B output files")


def clear_chroma_dir() -> None:
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
        log_with_timestamp(f"[OK] Removed Chroma directory: {CHROMA_DIR}")
    else:
        log_with_timestamp(f"[SKIP] Chroma directory not found: {CHROMA_DIR}")


def clear_neo4j_entities(
    neo4j_uri: str | None,
    neo4j_user: str | None,
    neo4j_password: str | None,
) -> None:
    if not neo4j_uri or not neo4j_password:
        raise RuntimeError("Neo4j URI and password are required for --reset-neo4j.")

    from load_neo4j import GraphDatabase

    if GraphDatabase is None:
        raise RuntimeError("neo4j package is not installed. Add neo4j to requirements.")

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        with driver.session() as session:
            session.run("MATCH (n:Entity) DETACH DELETE n")
        log_with_timestamp("[OK] Removed existing Neo4j (:Entity) graph data")
    finally:
        driver.close()


def extract_graphs_parallel(
    documents: list[dict[str, Any]],
    workers: int,
    extractor_mode: str,
    allow_fallback: bool,
    min_relation_score: float,
    force: bool,
) -> None:
    candidates = [doc for doc in documents if get_relation_relevance_score(doc) >= min_relation_score]
    skipped = len(documents) - len(candidates)
    if FAILURE_LOG_PATH.exists():
        FAILURE_LOG_PATH.unlink()

    started_at = time.time()
    failures = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                extract_one_graph,
                doc,
                extractor_mode,
                allow_fallback,
                force,
            ): doc
            for doc in candidates
        }
        for index, future in enumerate(as_completed(futures), start=1):
            doc = futures[future]
            try:
                output_path = future.result()
                log_with_timestamp(f"[OK] Graph {index}/{len(candidates)}: {output_path.name}")
            except Exception as exc:
                failures += 1
                append_failure(doc, exc)
                log_with_timestamp(f"[FAIL] Graph {index}/{len(candidates)}: {doc['source_id']} {exc}")

    elapsed = time.time() - started_at
    log_with_timestamp(
        f"[OK] Parallel extraction finished: candidates={len(candidates)} "
        f"skipped={skipped} failures={failures} elapsed={elapsed:.1f}s"
    )


def extract_one_graph(
    doc: dict[str, Any],
    extractor_mode: str,
    allow_fallback: bool,
    force: bool,
) -> Path:
    output_path = OUTPUT_DIR / f"{doc['source_id']}_graph.json"
    if output_path.exists() and not force:
        return output_path

    graph_data = extract_graph(doc, mode=extractor_mode, allow_fallback=allow_fallback)
    write_json_file(output_path, graph_data)
    return output_path


def append_failure(doc: dict[str, Any], exc: Exception) -> None:
    record = {
        "source_id": doc.get("source_id"),
        "dataset": doc.get("dataset") or doc.get("metadata", {}).get("dataset"),
        "error": repr(exc),
    }
    with FAILURE_LOG_PATH.open("a", encoding="utf-8") as failure_file:
        failure_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def rebuild_chroma(documents: list[dict[str, Any]]) -> None:
    client, collection = build_client_and_collection()
    embedding_function = OpenAIEmbeddingFunction()
    try:
        for index, doc in enumerate(documents, start=1):
            insert_doc_to_chroma_collection(
                collection,
                doc,
                source_name=doc["source_id"],
                embedding_function=embedding_function,
            )
            log_with_timestamp(f"[OK] Chroma {index}/{len(documents)}: {doc['source_id']}")
        log_with_timestamp(f"[OK] Chroma collection count: {collection.count()}")
    finally:
        client.close()


def load_outputs_to_neo4j_batch(
    neo4j_uri: str | None,
    neo4j_user: str | None,
    neo4j_password: str | None,
    batch_size: int,
) -> None:
    if not neo4j_uri or not neo4j_password:
        raise RuntimeError("Neo4j URI and password are required for Neo4j batch load.")

    graph_paths = sorted(OUTPUT_DIR.glob("*_graph.json"))
    graph_items = [load_graph_json(path) for path in graph_paths]
    load_graphs_to_neo4j_batch(graph_items, neo4j_uri, neo4j_user, neo4j_password, batch_size)
    log_with_timestamp(f"[OK] Neo4j batch load complete: {len(graph_items)} graph files")


def load_ftc_to_neo4j_batch(
    ftc_input: Path,
    neo4j_uri: str | None,
    neo4j_user: str | None,
    neo4j_password: str | None,
    batch_size: int,
) -> None:
    if not neo4j_uri or not neo4j_password:
        raise RuntimeError("Neo4j URI and password are required for FTC batch load.")

    graph_data = build_ftc_affiliates_graph(ftc_input)
    load_graphs_to_neo4j_batch([graph_data], neo4j_uri, neo4j_user, neo4j_password, batch_size)
    log_with_timestamp(f"[OK] FTC affiliate graph loaded: {graph_data['source_id']}")


def get_relation_relevance_score(doc: dict[str, Any]) -> float:
    value = doc.get("relation_relevance_score")
    if value is None and isinstance(doc.get("metadata"), dict):
        value = doc["metadata"].get("relation_relevance_score")

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    main()
