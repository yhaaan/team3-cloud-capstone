from __future__ import annotations

import argparse
from pathlib import Path

from document_io import iter_input_documents, write_json_file
from graph_pipeline import extract_graph
from load_chroma import insert_doc_to_chroma
from load_neo4j import OUTPUT_DIR, export_cypher_payload, load_graph_to_neo4j


BASE_DIR = Path(__file__).resolve().parent
TEST_DATA_DIR = BASE_DIR.parent / "tests"


def run_for_document(
    doc: dict[str, str],
    extractor_mode: str,
    use_chroma: bool,
    use_neo4j: bool,
    neo4j_uri: str | None,
    neo4j_user: str | None,
    neo4j_password: str | None,
) -> None:
    if use_chroma:
        insert_doc_to_chroma(doc, source_name=doc["source_id"])

    graph_data = extract_graph(doc, mode=extractor_mode)

    graph_output_path = OUTPUT_DIR / f"{doc['source_id']}_graph.json"
    write_json_file(graph_output_path, graph_data)

    cypher_output_path = OUTPUT_DIR / f"{doc['source_id']}_graph.cypher.txt"
    export_cypher_payload(graph_data, cypher_output_path)

    if use_neo4j and neo4j_uri and neo4j_user and neo4j_password:
        load_graph_to_neo4j(graph_data, neo4j_uri, neo4j_user, neo4j_password)
        print(f"[OK] Neo4j 적재 완료: {doc['source_id']}")
    else:
        print(f"[OK] Neo4j 산출물 생성 완료: {cypher_output_path.name}")

    print(f"[OK] 그래프 산출물 생성 완료: {graph_output_path.name}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Module B pipeline runner")
    parser.add_argument(
        "--input",
        type=Path,
        default=TEST_DATA_DIR,
        help="입력 JSON/JSONL 파일 또는 디렉터리",
    )
    parser.add_argument(
        "--extractor",
        choices=["rule", "openai"],
        default="rule",
        help="그래프 추출 방식",
    )
    parser.add_argument("--skip-chroma", action="store_true", help="Chroma 적재 건너뛰기")
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
        )
