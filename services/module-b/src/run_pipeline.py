from __future__ import annotations

import argparse
from pathlib import Path

from document_io import iter_input_documents, write_json_file
from graph_pipeline import extract_graph
from load_chroma import insert_doc_to_chroma, insert_doc_to_chroma_collection
from load_neo4j import OUTPUT_DIR, export_cypher_payload, load_graph_json, load_graph_to_neo4j


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent.parent
MODULE_A_DATA_DIR = ROOT_DIR / "services" / "module-a" / "data"


def run_for_document(
    doc: dict[str, str],
    extractor_mode: str,
    use_chroma: bool,
    use_neo4j: bool,
    neo4j_uri: str | None,
    neo4j_user: str | None,
    neo4j_password: str | None,
    allow_fallback: bool,
    min_relation_score: float = 0.6,
    chroma_collection: object | None = None,
    force_graph: bool = False,
) -> None:
    if use_chroma:
        if chroma_collection is None:
            insert_doc_to_chroma(doc, source_name=doc["source_id"])
        else:
            insert_doc_to_chroma_collection(
                chroma_collection,
                doc,
                source_name=doc["source_id"],
            )

    relation_score = get_relation_relevance_score(doc)
    if relation_score < min_relation_score:
        print(
            "[SKIP] Graph extraction skipped: "
            f"{doc['source_id']} relation_relevance_score={relation_score:.3f} "
            f"< {min_relation_score:.3f}"
        )
        return

    graph_output_path = OUTPUT_DIR / f"{doc['source_id']}_graph.json"
    if graph_output_path.exists() and not force_graph:
        graph_data = load_graph_json(graph_output_path, doc)
        print(f"[SKIP] Graph extraction reused existing output: {graph_output_path.name}")
    else:
        graph_data = extract_graph(doc, mode=extractor_mode, allow_fallback=allow_fallback)
        write_json_file(graph_output_path, graph_data)

    cypher_output_path = OUTPUT_DIR / f"{doc['source_id']}_graph.cypher.txt"
    export_cypher_payload(graph_data, cypher_output_path)

    if use_neo4j and neo4j_uri and neo4j_user and neo4j_password:
        load_graph_to_neo4j(graph_data, neo4j_uri, neo4j_user, neo4j_password)
        print(f"[OK] Neo4j 적재 완료: {doc['source_id']}")
    else:
        print(f"[OK] Neo4j 산출물 생성 완료: {cypher_output_path.name}")

    print(f"[OK] 그래프 산출물 생성 완료: {graph_output_path.name}")

def get_relation_relevance_score(doc: dict[str, str]) -> float:
    value = doc.get("relation_relevance_score")
    if value is None and isinstance(doc.get("metadata"), dict):
        value = doc["metadata"].get("relation_relevance_score")

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Module B pipeline runner")
    parser.add_argument(
        "--input",
        type=Path,
        default=MODULE_A_DATA_DIR,
        help="입력 JSON/JSONL 파일 또는 디렉터리",
    )
    parser.add_argument(
        "--extractor",
        choices=["rule", "openai"],
        default="openai",
        help="그래프 추출 방식",
    )
    parser.add_argument("--skip-chroma", action="store_true", help="Chroma 적재 건너뛰기")
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="OpenAI 추출 실패 시 규칙 기반 추출로 대체하지 않고 오류를 발생시킴",
    )
    parser.add_argument(
        "--min-relation-score",
        type=float,
        default=0.6,
        help="Minimum relation_relevance_score required for graph extraction",
    )
    parser.add_argument(
        "--force-graph",
        action="store_true",
        help="Regenerate graph JSON even when an output file already exists.",
    )
    parser.add_argument("--neo4j-uri", default=None)
    parser.add_argument("--neo4j-user", default=None)
    parser.add_argument("--neo4j-password", default=None)
    return parser


if __name__ == "__main__":
    args = build_argument_parser().parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    documents = iter_input_documents(args.input)
    for doc in documents:
        run_for_document(
            doc=doc,
            extractor_mode=args.extractor,
            use_chroma=not args.skip_chroma,
            use_neo4j=bool(args.neo4j_uri and args.neo4j_user and args.neo4j_password),
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            allow_fallback=not args.no_fallback,
            min_relation_score=args.min_relation_score,
            force_graph=args.force_graph,
        )
