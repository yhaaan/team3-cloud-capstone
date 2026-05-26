from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from company_whitelist import normalize_company_name, normalize_stock_code
from document_io import iter_input_documents, write_json_file
from ftc_affiliates import build_affiliate_group_id, normalize_yyyymmdd
from load_neo4j import OUTPUT_DIR, export_cypher_payload, load_graphs_to_neo4j_batch
from role_normalizer import build_company_id


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent.parent
DEFAULT_EXTRA_COMPANY_DIR = ROOT_DIR / "services" / "module-a" / "data" / "_extra_company"
DEFAULT_FTC_ALL_PATH = ROOT_DIR / "docs" / "ftc_affiliates_all.jsonl"
SOURCE_ID = "extra_company_company_membership_remaining"
FTC_SOURCE_NAME = "ftc_affiliates_all"
LEGAL_SUFFIX_PATTERN = re.compile(r"\(주\)|㈜|주식회사|\s+")


def clean_company_name(value: Any) -> str:
    cleaned = LEGAL_SUFFIX_PATTERN.sub("", str(value or ""))
    return normalize_company_name(cleaned)


def load_ftc_records_by_name(file_path: Path) -> dict[str, dict[str, Any]]:
    records_by_name: dict[str, dict[str, Any]] = {}
    with file_path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            key = clean_company_name(record.get("entrprsNm"))
            if key:
                records_by_name.setdefault(key, record)
    return records_by_name


def build_extra_company_membership_graph(
    input_path: Path,
    ftc_input: Path,
    skip_existing_cypher: bool,
) -> dict[str, Any]:
    documents = iter_input_documents(input_path)
    ftc_records_by_name = load_ftc_records_by_name(ftc_input)

    entities_by_id: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    seen_relations: set[tuple[str, str, str]] = set()
    included_count = 0
    matched_count = 0

    for doc in documents:
        if doc.get("dataset") != "business_segments":
            continue

        source_id = str(doc.get("source_id") or "")
        if skip_existing_cypher and (OUTPUT_DIR / f"{source_id}_graph.cypher.txt").exists():
            continue

        stock_code = normalize_stock_code(str(doc.get("stock_code") or ""))
        company_name = str(doc.get("company_name") or "").strip()
        if not stock_code or not company_name:
            continue

        included_count += 1
        company_id = build_company_id(stock_code)
        entities_by_id.setdefault(
            company_id,
            {
                "id": company_id,
                "type": "Company",
                "name": company_name,
                "stock_code": stock_code,
                "source": "module_a_extra_company",
            },
        )

        ftc_record = ftc_records_by_name.get(clean_company_name(company_name))
        if ftc_record is None:
            continue

        matched_count += 1
        group_name = str(ftc_record.get("unityGrupNm") or "").strip()
        group_id = build_affiliate_group_id(group_name)
        entities_by_id.setdefault(
            group_id,
            {
                "id": group_id,
                "type": "AffiliateGroup",
                "name": group_name,
                "presentn_year": str(ftc_record.get("presentnYear") or "").strip(),
                "source": FTC_SOURCE_NAME,
            },
        )

        relation_key = ("MEMBER_OF", company_id, group_id)
        if relation_key in seen_relations:
            continue
        seen_relations.add(relation_key)
        relations.append(
            {
                "type": "MEMBER_OF",
                "from": company_id,
                "to": group_id,
                "evidence": (
                    f"FTC {ftc_record.get('presentnYear')}: "
                    f"{company_name} is listed as a member of {group_name}."
                ),
                "presentn_year": str(ftc_record.get("presentnYear") or "").strip(),
                "jurirno": str(ftc_record.get("jurirno") or "").strip(),
                "bizrno": str(ftc_record.get("bizrno") or "").strip(),
                "representative_name": str(ftc_record.get("rprsntvNm") or "").strip(),
                "founded_on": normalize_yyyymmdd(ftc_record.get("fondDe")),
                "joined_on": normalize_yyyymmdd(ftc_record.get("grinil")),
                "source": FTC_SOURCE_NAME,
            }
        )

    graph_data = {
        "source_id": SOURCE_ID,
        "entities": list(entities_by_id.values()),
        "relations": relations,
        "metadata": {
            "input_path": input_path.as_posix(),
            "ftc_input": ftc_input.as_posix(),
            "skip_existing_cypher": skip_existing_cypher,
            "included_company_count": included_count,
            "matched_affiliate_group_count": matched_count,
        },
    }
    return graph_data


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load _extra_company Company nodes and FTC affiliate memberships only."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_EXTRA_COMPANY_DIR)
    parser.add_argument("--ftc-input", type=Path, default=DEFAULT_FTC_ALL_PATH)
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Include documents that already have per-document graph cypher outputs.",
    )
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser


def main() -> None:
    load_dotenv(override=True)
    args = build_argument_parser().parse_args()

    graph_data = build_extra_company_membership_graph(
        input_path=args.input,
        ftc_input=args.ftc_input,
        skip_existing_cypher=not args.include_existing,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    graph_output_path = OUTPUT_DIR / f"{SOURCE_ID}_graph.json"
    cypher_output_path = OUTPUT_DIR / f"{SOURCE_ID}_graph.cypher.txt"
    write_json_file(graph_output_path, graph_data)
    export_cypher_payload(graph_data, cypher_output_path)

    print(
        "[OK] Extra company membership graph built: "
        f"companies={graph_data['metadata']['included_company_count']} "
        f"affiliate_memberships={len(graph_data['relations'])}"
    )

    if args.export_only:
        return

    if not args.neo4j_uri or not args.neo4j_password:
        raise RuntimeError(
            "Neo4j URI and password are required. Set NEO4J_URI and NEO4J_PASSWORD "
            "in .env or pass --neo4j-uri/--neo4j-password."
        )

    load_graphs_to_neo4j_batch(
        [graph_data],
        args.neo4j_uri,
        args.neo4j_user,
        args.neo4j_password,
        args.batch_size,
    )
    print("[OK] Extra company membership graph loaded into Neo4j")


if __name__ == "__main__":
    main()
