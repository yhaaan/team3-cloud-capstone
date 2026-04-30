from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

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
SET r.evidence = $evidence
"""


def load_graph_json(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


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
                "evidence": relation["evidence"],
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
                    evidence=relation["evidence"],
                )
    finally:
        driver.close()


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
    return parser


if __name__ == "__main__":
    args = build_argument_parser().parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.input.is_dir():
        file_paths = sorted(args.input.glob("*_graph.json"))
    else:
        file_paths = [args.input]

    for file_path in file_paths:
        graph_data = load_graph_json(file_path)
        cypher_path = OUTPUT_DIR / f"{file_path.stem}.cypher.txt"
        export_cypher_payload(graph_data, cypher_path)
        print(f"[OK] Neo4j ?곸옱??Cypher ?대낫?닿린 ?꾨즺: {cypher_path}")

        if args.export_only:
            continue

        if not args.uri or not args.password:
            print("[SKIP] NEO4J_URI 또는 NEO4J_PASSWORD가 없어 실제 적재는 건너뜁니다")
            continue

        load_graph_to_neo4j(graph_data, args.uri, args.user, args.password)
        print(f"[OK] Neo4j ?곸옱 ?꾨즺: {file_path.name}")

