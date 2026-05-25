from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from log_utils import log_with_timestamp

from company_whitelist import load_default_company_whitelist
from ftc_affiliates import DEFAULT_FTC_AFFILIATES_PATH, build_ftc_affiliates_graph
from role_normalizer import normalize_graph_roles

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

load_dotenv(override=True)


BASE_DIR = Path(__file__).resolve().parent
MODULE_B_DIR = BASE_DIR.parent
OUTPUT_DIR = MODULE_B_DIR / "outputs"


NODE_QUERY = """
MERGE (n:Entity {id: $id})
SET n += $properties
SET n:`%s`
"""

RELATION_QUERY = """
MATCH (source:Entity {id: $from_id})
MATCH (target:Entity {id: $to_id})
MERGE (source)-[r:%s]->(target)
SET r += $properties
"""

BATCH_NODE_QUERY = """
UNWIND $rows AS row
MERGE (n:Entity {id: row.id})
SET n += row.properties
SET n:`%s`
"""

BATCH_RELATION_QUERY = """
UNWIND $rows AS row
MATCH (source:Entity {id: row.from_id})
MATCH (target:Entity {id: row.to_id})
MERGE (source)-[r:%s]->(target)
SET r += row.properties
"""


def load_graph_json(file_path: Path, source_doc: dict[str, Any] | None = None) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        return normalize_graph_roles(
            json.load(file),
            load_default_company_whitelist(),
            source_doc,
        )


def export_cypher_payload(graph_data: dict[str, Any], output_path: Path) -> None:
    lines: list[str] = []

    for entity in graph_data["entities"]:
        properties = json.dumps(entity, ensure_ascii=False)
        lines.append(f"// node: {entity['id']}")
        lines.append(NODE_QUERY % entity["type"])
        lines.append(f":params {properties}")
        lines.append("")

    for relation in graph_data["relations"]:
        params = json.dumps(
            {
                "from_id": relation["from"],
                "to_id": relation["to"],
                "properties": build_relation_properties(relation),
            },
            ensure_ascii=False,
        )
        lines.append(f"// relation: {relation['type']}")
        lines.append(RELATION_QUERY % relation["type"])
        lines.append(f":params {params}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def load_graph_to_neo4j(
    graph_data: dict[str, Any],
    uri: str,
    user: str,
    password: str,
) -> None:
    if GraphDatabase is None:
        raise RuntimeError("neo4j ?⑦궎吏媛 ?ㅼ튂?섏? ?딆븯?듬땲?? requirements??neo4j瑜?異붽??섏꽭??")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            for entity in graph_data["entities"]:
                session.run(
                    NODE_QUERY % entity["type"],
                    id=entity["id"],
                    properties=entity,
                )

            for relation in graph_data["relations"]:
                session.run(
                    RELATION_QUERY % relation["type"],
                    from_id=relation["from"],
                    to_id=relation["to"],
                    properties=build_relation_properties(relation),
                )
    finally:
        driver.close()


def load_graphs_to_neo4j_batch(
    graph_items: list[dict[str, Any]],
    uri: str,
    user: str,
    password: str,
    batch_size: int = 1000,
) -> None:
    if GraphDatabase is None:
        raise RuntimeError("neo4j package is not installed. Add neo4j to requirements.")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            for entity_type, rows in group_entity_rows(graph_items).items():
                for batch in chunked(rows, batch_size):
                    session.run(BATCH_NODE_QUERY % entity_type, rows=batch)

            for relation_type, rows in group_relation_rows(graph_items).items():
                for batch in chunked(rows, batch_size):
                    session.run(BATCH_RELATION_QUERY % relation_type, rows=batch)
    finally:
        driver.close()


def group_entity_rows(graph_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for graph_data in graph_items:
        for entity in graph_data.get("entities", []):
            entity_type = str(entity["type"])
            grouped.setdefault(entity_type, {})[entity["id"]] = {
                "id": entity["id"],
                "properties": entity,
            }

    return {entity_type: list(rows_by_id.values()) for entity_type, rows_by_id in grouped.items()}


def group_relation_rows(graph_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for graph_data in graph_items:
        for relation in graph_data.get("relations", []):
            relation_type = str(relation["type"])
            relation_key = (str(relation["from"]), str(relation["to"]))
            grouped.setdefault(relation_type, {})[relation_key] = {
                "from_id": relation["from"],
                "to_id": relation["to"],
                "properties": build_relation_properties(relation),
            }

    return {relation_type: list(rows_by_key.values()) for relation_type, rows_by_key in grouped.items()}


def chunked(rows: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    size = max(1, batch_size)
    return [rows[start : start + size] for start in range(0, len(rows), size)]


def build_relation_properties(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in relation.items()
        if key not in {"type", "from", "to"}
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Module B Neo4j loader")
    parser.add_argument(
        "--input",
        type=Path,
        default=OUTPUT_DIR,
        help="洹몃옒??JSON ?뚯씪 ?먮뒗 ?붾젆?곕━ 寃쎈줈",
    )
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI"))
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Cypher ?뚯씪留??앹꽦?섍퀬 ?ㅼ젣 ?곸옱???섏? ?딆쓬",
    )
    parser.add_argument(
        "--ftc-affiliates",
        action="store_true",
        help="Load FTC listed affiliate-group membership graph from docs/ftc_affiliates.jsonl.",
    )
    parser.add_argument(
        "--ftc-input",
        type=Path,
        default=DEFAULT_FTC_AFFILIATES_PATH,
        help="FTC affiliates jsonl path. Defaults to docs/ftc_affiliates.jsonl.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Load all selected graph JSON files with UNWIND batch queries.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Neo4j UNWIND row count per query when --batch is used.",
    )
    return parser


if __name__ == "__main__":
    args = build_argument_parser().parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.ftc_affiliates:
        graph_data = build_ftc_affiliates_graph(args.ftc_input)
        cypher_path = OUTPUT_DIR / f"{graph_data['source_id']}.cypher.txt"
        export_cypher_payload(graph_data, cypher_path)
        log_with_timestamp(f"[OK] FTC affiliate Cypher export complete: {cypher_path}")

        if not args.export_only:
            if not args.uri or not args.password:
                log_with_timestamp("[SKIP] NEO4J_URI ?? NEO4J_PASSWORD? ?? ?? ??? ?????")
            else:
                load_graph_to_neo4j(graph_data, args.uri, args.user, args.password)
                log_with_timestamp(f"[OK] FTC affiliate graph loaded: {graph_data['source_id']}")
        raise SystemExit(0)

    if args.input.is_dir():
        file_paths = sorted(args.input.glob("*_graph.json"))
    else:
        file_paths = [args.input]

    graph_items = [load_graph_json(file_path) for file_path in file_paths]

    for file_path, graph_data in zip(file_paths, graph_items):
        cypher_path = OUTPUT_DIR / f"{file_path.stem}.cypher.txt"
        export_cypher_payload(graph_data, cypher_path)
        log_with_timestamp(f"[OK] Neo4j Cypher export complete: {cypher_path}")

    if args.export_only:
        raise SystemExit(0)

    if not args.uri or not args.password:
        log_with_timestamp("[SKIP] NEO4J_URI ?? NEO4J_PASSWORD? ?? ?? ??? ?????")
        raise SystemExit(0)

    if args.batch:
        load_graphs_to_neo4j_batch(graph_items, args.uri, args.user, args.password, args.batch_size)
        log_with_timestamp(f"[OK] Neo4j batch load complete: {len(graph_items)} graph files")
    else:
        for file_path, graph_data in zip(file_paths, graph_items):
            load_graph_to_neo4j(graph_data, args.uri, args.user, args.password)
            log_with_timestamp(f"[OK] Neo4j load complete: {file_path.name}")
