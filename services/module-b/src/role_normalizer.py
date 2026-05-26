from __future__ import annotations

import re
from typing import Any

from company_whitelist import CompanyWhitelist, normalize_stock_code
from industry_taxonomy import IndustryTaxonomyEntry, load_default_industry_taxonomy


COMPANY_SUFFIX_PATTERN = re.compile(
    r"(주식회사|㈜|\(주\)|주\)|그룹|전자|중공업|하이닉스|바이오로직스|스퀘어|오션|현대|삼성|SK|LG|HD)",
    re.IGNORECASE,
)

ROLE_PATTERNS: list[tuple[str, str, tuple[str, ...]]] = [
    ("VICE_CHAIRMAN", "부회장", ("부회장", "vice chairman")),
    ("CHAIRMAN", "회장", ("회장", "chairman")),
    ("CEO", "대표이사", ("대표이사", "대표", "ceo", "chief executive officer")),
    ("VICE_PRESIDENT", "부사장", ("부사장", "vice president")),
    ("PRESIDENT", "사장", ("사장", "president")),
    ("BOARD_CHAIR", "이사회 의장", ("이사회 의장", "의장", "board chair")),
    ("OUTSIDE_DIRECTOR", "사외이사", ("사외이사", "outside director")),
    ("DIRECTOR", "이사", ("기타비상무이사", "사내이사", "이사", "director")),
    ("MAYOR", "시장", ("시장", "mayor")),
    ("MINISTER", "장관", ("장관", "minister")),
    ("RESEARCHER", "연구원", ("연구원", "researcher", "analyst")),
]

PERSON_RELATION_FIELDS = {
    "affiliated_company",
    "executive_type",
    "full_time_status",
    "major_shareholder_relation",
    "responsibility",
    "role",
    "role_label",
    "role_raw",
    "tenure",
    "tenure_end_on",
}

PERSON_IDENTITY_FIELDS = {
    "id",
    "type",
    "name",
    "birth_ym",
    "gender",
    "main_career",
}

PERSON_COMPANY_RELATION_TYPES = {"APPOINTED_TO", "AFFILIATED_WITH"}
EXECUTIVE_STATUS_COMPANY_RELATION_TYPES = {"ACQUIRES", "INVESTS_IN"}
LEGACY_BUSINESS_AREA_PREFIX = "business_area_"


def normalize_graph_roles(
    graph_data: dict[str, Any],
    company_whitelist: CompanyWhitelist | None = None,
    source_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    filter_non_dart_person_entities(graph_data, source_doc)
    migrate_person_entity_roles_to_source_company_relations(graph_data, source_doc)
    strip_person_relation_fields(graph_data)
    normalize_industry_taxonomy(graph_data)

    if company_whitelist is not None:
        canonicalize_company_entities(graph_data, company_whitelist)
        add_dart_executive_entities(graph_data, company_whitelist, source_doc)
        add_dart_major_shareholder_relations(graph_data, company_whitelist, source_doc)

    graph_data["entities"] = deduplicate_entities_by_id(graph_data.get("entities", []))
    if company_whitelist is not None:
        graph_data["entities"] = filter_allowed_companies(
            graph_data["entities"],
            company_whitelist,
        )
        if not any(entity.get("type") == "Company" for entity in graph_data["entities"]):
            graph_data["entities"] = []
            graph_data["relations"] = []
            return graph_data
    graph_data["relations"] = repair_relations(
        graph_data.get("relations", []),
        graph_data["entities"],
        company_whitelist=company_whitelist,
        source_doc=source_doc,
        source_id=str(graph_data.get("source_id") or ""),
    )
    return graph_data


def normalize_industry_taxonomy(graph_data: dict[str, Any]) -> None:
    id_mapping: dict[str, str] = {}
    taxonomy = load_default_industry_taxonomy()

    for entity in graph_data.get("entities", []):
        entity_id = str(entity.get("id") or "").strip()
        if entity.get("type") == "BusinessArea" or entity_id.startswith(LEGACY_BUSINESS_AREA_PREFIX):
            industry_id = remap_business_area_id(entity_id)
            entity["id"] = industry_id
            entity["type"] = "Industry"
            if entity_id and entity_id != industry_id:
                id_mapping[entity_id] = industry_id

        if entity.get("type") != "Industry":
            continue

        original_id = str(entity.get("id") or "").strip()
        taxonomy_entry = taxonomy.find(original_id, str(entity.get("name") or ""))
        if taxonomy_entry is None:
            continue

        entity["id"] = taxonomy_entry.id
        entity["name"] = taxonomy_entry.name
        if original_id and original_id != taxonomy_entry.id:
            id_mapping[original_id] = taxonomy_entry.id

    for relation in graph_data.get("relations", []):
        from_id = str(relation.get("from") or "").strip()
        to_id = str(relation.get("to") or "").strip()
        if from_id in id_mapping:
            relation["from"] = id_mapping[from_id]
        elif from_id.startswith(LEGACY_BUSINESS_AREA_PREFIX):
            relation["from"] = remap_business_area_id(from_id)

        if to_id in id_mapping:
            relation["to"] = id_mapping[to_id]
        elif to_id.startswith(LEGACY_BUSINESS_AREA_PREFIX):
            relation["to"] = remap_business_area_id(to_id)

        if relation.get("type") == "OPERATES_IN":
            relation["type"] = "BELONGS_TO"

    add_taxonomy_entities_and_relations(graph_data)


def remap_business_area_id(entity_id: str) -> str:
    if entity_id.startswith(LEGACY_BUSINESS_AREA_PREFIX):
        return "industry_" + entity_id.removeprefix(LEGACY_BUSINESS_AREA_PREFIX)
    return entity_id


def add_taxonomy_entities_and_relations(graph_data: dict[str, Any]) -> None:
    taxonomy = load_default_industry_taxonomy()
    industry_ids = {
        str(entity.get("id") or "")
        for entity in graph_data.get("entities", [])
        if entity.get("type") == "Industry"
    }
    if not industry_ids:
        return

    for industry_id in list(industry_ids):
        entry = taxonomy.get(industry_id)
        if entry is None:
            continue

        ensure_taxonomy_entity(graph_data, entry)
        for ancestor in taxonomy.ancestors(industry_id):
            ensure_taxonomy_entity(graph_data, ancestor)

        current = entry
        while current.parent_id:
            parent = taxonomy.get(current.parent_id)
            if parent is None:
                break
            ensure_taxonomy_relation(
                graph_data,
                "PART_OF",
                current.id,
                parent.id,
                f"Industry taxonomy: {current.name} is part of {parent.name}.",
            )
            current = parent

        for related_id in entry.related_ids:
            related = taxonomy.get(related_id)
            if related is None:
                continue
            ensure_taxonomy_entity(graph_data, related)
            ensure_taxonomy_relation(
                graph_data,
                "RELATED_TO",
                entry.id,
                related.id,
                f"Industry taxonomy: {entry.name} is related to {related.name}.",
            )


def ensure_taxonomy_entity(
    graph_data: dict[str, Any],
    entry: IndustryTaxonomyEntry,
) -> None:
    ensure_entity(
        graph_data,
        {
            "id": entry.id,
            "type": "Industry",
            "name": entry.name,
        },
    )


def ensure_taxonomy_relation(
    graph_data: dict[str, Any],
    relation_type: str,
    from_id: str,
    to_id: str,
    evidence: str,
) -> None:
    if not from_id or not to_id or from_id == to_id:
        return

    for relation in graph_data.setdefault("relations", []):
        if (
            relation.get("type") == relation_type
            and relation.get("from") == from_id
            and relation.get("to") == to_id
        ):
            return

    graph_data["relations"].append(
        {
            "type": relation_type,
            "from": from_id,
            "to": to_id,
            "evidence": evidence,
        }
    )

def strip_person_relation_fields(graph_data: dict[str, Any]) -> None:
    for entity in graph_data.get("entities", []):
        if entity.get("type") != "Person":
            continue
        for key in list(entity.keys()):
            if key in PERSON_RELATION_FIELDS or key not in PERSON_IDENTITY_FIELDS:
                entity.pop(key, None)


def migrate_person_entity_roles_to_source_company_relations(
    graph_data: dict[str, Any],
    source_doc: dict[str, Any] | None = None,
) -> None:
    source_company_id = infer_source_company_id(graph_data, source_doc)
    if not source_company_id:
        return

    person_fields_by_id = {}
    for entity in graph_data.get("entities", []):
        if entity.get("type") != "Person":
            continue
        fields = {
            key: value
            for key, value in entity.items()
            if key in PERSON_RELATION_FIELDS and value
        }
        if fields:
            person_fields_by_id[str(entity.get("id") or "")] = fields

    if not person_fields_by_id:
        return

    for relation in graph_data.get("relations", []):
        if relation.get("type") not in PERSON_COMPANY_RELATION_TYPES:
            continue
        if relation.get("to") != source_company_id:
            continue
        fields = person_fields_by_id.get(str(relation.get("from") or ""))
        if not fields:
            continue
        for key, value in fields.items():
            if value and not relation.get(key):
                relation[key] = value


def infer_source_company_id(
    graph_data: dict[str, Any],
    source_doc: dict[str, Any] | None = None,
) -> str:
    stock_code = ""
    if source_doc is not None:
        stock_code = str(source_doc.get("stock_code") or "")

    if not stock_code:
        source_id = str((source_doc or graph_data).get("source_id") or "")
        match = re.match(r"dart_(\d{6})_", source_id)
        if match:
            stock_code = match.group(1)

    if not stock_code:
        return ""
    return build_company_id(stock_code)


def filter_non_dart_person_entities(
    graph_data: dict[str, Any],
    source_doc: dict[str, Any] | None = None,
) -> None:
    if allows_person_entities(source_doc, graph_data):
        return

    removed_person_ids = {
        str(entity.get("id") or "")
        for entity in graph_data.get("entities", [])
        if entity.get("type") == "Person"
    }
    if not removed_person_ids:
        return

    graph_data["entities"] = [
        entity for entity in graph_data.get("entities", []) if entity.get("type") != "Person"
    ]
    graph_data["relations"] = [
        relation
        for relation in graph_data.get("relations", [])
        if relation.get("from") not in removed_person_ids
        and relation.get("to") not in removed_person_ids
    ]


def allows_person_entities(
    source_doc: dict[str, Any] | None = None,
    graph_data: dict[str, Any] | None = None,
) -> bool:
    if not source_doc:
        source_id = str((graph_data or {}).get("source_id") or "")
        return source_id.startswith("dart_") and "_executive_status_" in source_id

    source_type = str(
        source_doc.get("document_type") or source_doc.get("module_a_type") or ""
    )
    dataset = str(source_doc.get("dataset") or "")
    if not dataset and isinstance(source_doc.get("metadata"), dict):
        dataset = str(source_doc["metadata"].get("dataset") or "")

    return source_type == "dart" and dataset == "executive_status"


def add_dart_executive_entities(
    graph_data: dict[str, Any],
    company_whitelist: CompanyWhitelist,
    source_doc: dict[str, Any] | None = None,
) -> None:
    if not source_doc or source_doc.get("dataset") != "executive_status":
        return

    records = source_doc.get("normalized_records")
    if records is None and isinstance(source_doc.get("metadata"), dict):
        records = source_doc["metadata"].get("normalized_records")
    if not isinstance(records, list):
        return

    listed_company = company_whitelist.find(
        name=str(source_doc.get("company_name") or ""),
        stock_code=str(source_doc.get("stock_code") or ""),
    )
    if listed_company is None:
        return

    company_id = build_company_id(listed_company.stock_code)
    ensure_entity(
        graph_data,
        {
            "id": company_id,
            "type": "Company",
            "name": listed_company.company_name,
            "stock_code": normalize_stock_code(listed_company.stock_code),
        },
    )

    for record in records:
        if not isinstance(record, dict):
            continue

        person_name = string_value(record.get("nm")).strip()
        if not person_name:
            continue

        birth_ym = normalize_birth_ym(record.get("birth_ym"))
        person_id = build_person_id(person_name, birth_ym)
        remap_existing_person_entities(graph_data, person_name, person_id)
        role_raw = string_value(record.get("ofcps")).strip()
        person_entity = {
            "id": person_id,
            "type": "Person",
            "name": person_name,
        }
        add_if_present(person_entity, "birth_ym", birth_ym)
        add_if_present(person_entity, "gender", record.get("sexdstn"))
        add_if_present(person_entity, "main_career", record.get("main_career"))
        ensure_entity(graph_data, person_entity)

        evidence = build_executive_evidence(record, listed_company.company_name)
        relation = {
            "type": "AFFILIATED_WITH",
            "from": person_id,
            "to": company_id,
            "evidence": evidence,
        }
        add_person_company_relation_fields(relation, record)
        ensure_relation(
            graph_data,
            relation,
        )


def add_dart_major_shareholder_relations(
    graph_data: dict[str, Any],
    company_whitelist: CompanyWhitelist,
    source_doc: dict[str, Any] | None = None,
) -> None:
    if not source_doc or get_source_dataset(source_doc) != "major_shareholder_status":
        return

    records = source_doc.get("normalized_records")
    if records is None and isinstance(source_doc.get("metadata"), dict):
        records = source_doc["metadata"].get("normalized_records")
    if not isinstance(records, list):
        return

    target_company = company_whitelist.find(
        name=str(source_doc.get("company_name") or ""),
        stock_code=str(source_doc.get("stock_code") or ""),
    )
    if target_company is None:
        return

    target_company_id = build_company_id(target_company.stock_code)
    ensure_entity(
        graph_data,
        {
            "id": target_company_id,
            "type": "Company",
            "name": target_company.company_name,
            "stock_code": normalize_stock_code(target_company.stock_code),
        },
    )

    for record in records:
        if not isinstance(record, dict):
            continue

        shareholder_name = string_value(record.get("nm")).strip()
        if not shareholder_name or is_total_shareholder_record(shareholder_name):
            continue

        shareholder_company = company_whitelist.find(name=shareholder_name)
        if shareholder_company is None:
            continue

        shareholder_company_id = build_company_id(shareholder_company.stock_code)
        if shareholder_company_id == target_company_id:
            continue

        ensure_entity(
            graph_data,
            {
                "id": shareholder_company_id,
                "type": "Company",
                "name": shareholder_company.company_name,
                "stock_code": normalize_stock_code(shareholder_company.stock_code),
            },
        )

        relation = {
            "type": "INVESTS_IN",
            "from": shareholder_company_id,
            "to": target_company_id,
            "evidence": build_major_shareholder_evidence(record, target_company.company_name),
        }
        add_if_present(relation, "major_shareholder_relation", record.get("relate"))
        add_if_present(relation, "shares_held", record.get("trmend_posesn_stock_co"))
        add_if_present(relation, "ownership_ratio", record.get("trmend_posesn_stock_qota_rt"))
        add_if_present(relation, "settlement_date", normalize_korean_date(record.get("stlm_dt")))
        ensure_relation(graph_data, relation)


def get_source_dataset(source_doc: dict[str, Any]) -> str:
    dataset = str(source_doc.get("dataset") or "")
    if not dataset and isinstance(source_doc.get("metadata"), dict):
        dataset = str(source_doc["metadata"].get("dataset") or "")
    return dataset


def is_total_shareholder_record(name: str) -> bool:
    normalized = re.sub(r"\s+", "", name).strip()
    return normalized in {"\uacc4", "\ud569\uacc4", "total", "sum"}


def build_major_shareholder_evidence(record: dict[str, Any], target_company_name: str) -> str:
    shareholder_name = string_value(record.get("nm")).strip()
    relation = string_value(record.get("relate")).strip()
    shares = string_value(record.get("trmend_posesn_stock_co")).strip()
    ratio = string_value(record.get("trmend_posesn_stock_qota_rt")).strip()

    parts = [
        f"{shareholder_name} is listed as a major shareholder of {target_company_name}",
    ]
    if relation and relation != "-":
        parts.append(f"relation={relation}")
    if shares and shares != "-":
        parts.append(f"shares_held={shares}")
    if ratio and ratio != "-":
        parts.append(f"ownership_ratio={ratio}%")
    return ", ".join(parts) + "."


def add_person_company_relation_fields(
    relation: dict[str, Any],
    record: dict[str, Any],
) -> None:
    role_raw = string_value(record.get("ofcps")).strip()
    if role_raw:
        role_code, role_label = normalize_role(role_raw)
        relation["role_raw"] = role_raw
        relation["role"] = role_code
        relation["role_label"] = role_label

    add_if_present(relation, "board_role", record.get("rgist_exctv_at"))
    add_if_present(relation, "full_time_status", record.get("fte_at"))
    add_if_present(relation, "responsibility", record.get("chrg_job"))
    add_if_present(relation, "major_shareholder_relation", record.get("mxmm_shrholdr_relate"))
    add_if_present(relation, "tenure", record.get("hffc_pd"))
    add_if_present(relation, "tenure_end_on", normalize_korean_date(record.get("tenure_end_on")))


def remap_existing_person_entities(
    graph_data: dict[str, Any],
    person_name: str,
    canonical_person_id: str,
) -> None:
    old_ids: set[str] = set()
    for entity in graph_data.get("entities", []):
        if entity.get("type") != "Person":
            continue
        if entity.get("id") == canonical_person_id:
            continue
        if string_value(entity.get("name")).strip() == person_name:
            old_id = string_value(entity.get("id")).strip()
            if old_id:
                old_ids.add(old_id)
            entity["id"] = canonical_person_id

    if not old_ids:
        return

    for relation in graph_data.get("relations", []):
        if relation.get("from") in old_ids:
            relation["from"] = canonical_person_id
        if relation.get("to") in old_ids:
            relation["to"] = canonical_person_id


def ensure_entity(graph_data: dict[str, Any], entity: dict[str, Any]) -> None:
    entities = graph_data.setdefault("entities", [])
    entity_id = str(entity.get("id") or "")
    for existing in entities:
        if existing.get("id") != entity_id:
            continue
        for key, value in entity.items():
            if value and not existing.get(key):
                existing[key] = value
        return
    entities.append(entity)


def ensure_relation(graph_data: dict[str, Any], relation: dict[str, Any]) -> None:
    relations = graph_data.setdefault("relations", [])
    relation_key = (
        relation.get("type"),
        relation.get("from"),
        relation.get("to"),
        relation.get("evidence"),
    )
    for existing in relations:
        existing_key = (
            existing.get("type"),
            existing.get("from"),
            existing.get("to"),
            existing.get("evidence"),
        )
        if existing_key == relation_key:
            for key, value in relation.items():
                if value and not existing.get(key):
                    existing[key] = value
            return
    relations.append(relation)


def add_if_present(entity: dict[str, Any], key: str, value: Any) -> None:
    cleaned = string_value(value).strip()
    if cleaned and cleaned != "-":
        entity[key] = cleaned


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def normalize_birth_ym(value: Any) -> str:
    text = string_value(value).strip()
    match = re.search(r"(\d{4})\D+(\d{1,2})", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return text


def normalize_korean_date(value: Any) -> str:
    text = string_value(value).strip()
    match = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return text


def build_person_id(name: str, birth_ym: str) -> str:
    normalized_name = re.sub(r"[^0-9A-Za-z가-힣]+", "_", name.strip()).strip("_").lower()
    normalized_birth_ym = re.sub(r"[^0-9]+", "", birth_ym)
    if normalized_birth_ym:
        return f"person_{normalized_name}_{normalized_birth_ym}"
    return f"person_{normalized_name}"


def build_executive_evidence(record: dict[str, Any], company_name: str) -> str:
    parts = [
        string_value(record.get("nm")).strip(),
        company_name,
        string_value(record.get("ofcps")).strip(),
        string_value(record.get("rgist_exctv_at")).strip(),
        string_value(record.get("birth_ym")).strip(),
    ]
    return " ".join(part for part in parts if part and part != "-")


def canonicalize_company_entities(
    graph_data: dict[str, Any],
    company_whitelist: CompanyWhitelist,
) -> None:
    id_mapping: dict[str, str] = {}

    for entity in graph_data.get("entities", []):
        if entity.get("type") != "Company":
            continue

        original_id = str(entity.get("id") or "").strip()
        listed_company = company_whitelist.find(
            name=str(entity.get("name") or ""),
            stock_code=str(entity.get("stock_code") or ""),
        )
        if listed_company is None:
            continue

        canonical_id = build_company_id(listed_company.stock_code)
        entity["id"] = canonical_id
        entity["name"] = listed_company.company_name
        entity["stock_code"] = normalize_stock_code(listed_company.stock_code)
        if original_id and original_id != canonical_id:
            id_mapping[original_id] = canonical_id

    if not id_mapping:
        return

    for relation in graph_data.get("relations", []):
        from_id = str(relation.get("from") or "").strip()
        to_id = str(relation.get("to") or "").strip()
        if from_id in id_mapping:
            relation["from"] = id_mapping[from_id]
        if to_id in id_mapping:
            relation["to"] = id_mapping[to_id]


def build_company_id(stock_code: str) -> str:
    return f"company_{normalize_stock_code(stock_code)}"


def normalize_role(raw_role: str) -> tuple[str, str]:
    cleaned = clean_role_text(raw_role)
    lowered = cleaned.lower()

    for role_code, role_label, aliases in ROLE_PATTERNS:
        if any(alias.lower() in lowered for alias in aliases):
            return role_code, role_label

    return "OTHER", cleaned or raw_role


def clean_role_text(raw_role: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw_role).strip()
    cleaned = re.sub(r"\([^)]*\)", "", cleaned).strip()

    tokens = [
        token
        for token in re.split(r"\s+", cleaned)
        if token and not COMPANY_SUFFIX_PATTERN.search(token)
    ]
    return " ".join(tokens).strip() or cleaned


def deduplicate_entities_by_id(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for entity in entities:
        entity_id = str(entity.get("id") or "").strip()
        if not entity_id:
            continue

        if entity_id not in merged:
            merged[entity_id] = dict(entity)
            continue

        current = merged[entity_id]
        for key, value in entity.items():
            if value and not current.get(key):
                current[key] = value

    return list(merged.values())


def repair_relations(
    relations: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    company_whitelist: CompanyWhitelist | None = None,
    source_doc: dict[str, Any] | None = None,
    source_id: str = "",
) -> list[dict[str, Any]]:
    entity_by_id = {entity["id"]: entity for entity in entities if entity.get("id")}
    repaired: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for relation in relations:
        from_id = str(relation.get("from") or "").strip()
        to_id = str(relation.get("to") or "").strip()
        evidence = str(relation.get("evidence") or "").strip()

        if not from_id or not to_id or not evidence:
            continue

        ensure_endpoint_entity(from_id, entity_by_id, entities, company_whitelist)
        ensure_endpoint_entity(to_id, entity_by_id, entities, company_whitelist)

        if from_id not in entity_by_id or to_id not in entity_by_id:
            continue

        if should_drop_relation(relation, entity_by_id, source_doc, source_id):
            continue

        relation_key = (relation.get("type", ""), from_id, to_id, evidence)
        if relation_key in seen:
            continue
        seen.add(relation_key)

        repaired_relation = dict(relation)
        repaired_relation["from"] = from_id
        repaired_relation["to"] = to_id
        repaired_relation["evidence"] = evidence
        normalize_person_company_relation(repaired_relation, entity_by_id)
        if source_doc is not None:
            repaired_relation.update(build_evidence_source(source_doc))
        repaired.append(repaired_relation)

    return filter_industry_taxonomy_relations(repaired, entity_by_id)


def filter_industry_taxonomy_relations(
    relations: list[dict[str, Any]],
    entity_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    part_of_industry_pairs = {
        (str(relation.get("from") or ""), str(relation.get("to") or ""))
        for relation in relations
        if relation.get("type") == "PART_OF"
        and is_industry_relation(relation, entity_by_id)
        and relation.get("from") != relation.get("to")
    }

    filtered: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for relation in relations:
        relation_type = str(relation.get("type") or "")
        from_id = str(relation.get("from") or "")
        to_id = str(relation.get("to") or "")

        if not is_valid_industry_taxonomy_relation(relation, entity_by_id):
            continue

        if relation_type in {"PART_OF", "RELATED_TO"} and from_id == to_id:
            continue

        if relation_type == "RELATED_TO" and is_industry_relation(relation, entity_by_id):
            if (from_id, to_id) in part_of_industry_pairs or (to_id, from_id) in part_of_industry_pairs:
                continue

        key = (
            relation_type,
            from_id,
            to_id,
            str(relation.get("evidence") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        filtered.append(relation)

    return filtered


def is_valid_industry_taxonomy_relation(
    relation: dict[str, Any],
    entity_by_id: dict[str, dict[str, Any]],
) -> bool:
    relation_type = str(relation.get("type") or "")
    if relation_type not in {"BELONGS_TO", "PRODUCES", "PART_OF", "RELATED_TO"}:
        return True

    from_type = entity_type_for_relation_endpoint(relation.get("from"), entity_by_id)
    to_type = entity_type_for_relation_endpoint(relation.get("to"), entity_by_id)

    if relation_type == "BELONGS_TO":
        return from_type == "Company" and to_type == "Industry"
    if relation_type == "PRODUCES":
        return from_type == "Company" and to_type == "ProductService"
    if relation_type == "PART_OF":
        return from_type in {"Industry", "ProductService"} and to_type == "Industry"
    if relation_type == "RELATED_TO":
        return from_type == "Industry" and to_type == "Industry"
    return True


def entity_type_for_relation_endpoint(
    entity_id: Any,
    entity_by_id: dict[str, dict[str, Any]],
) -> str:
    entity = entity_by_id.get(str(entity_id or ""))
    return str((entity or {}).get("type") or "")


def is_industry_relation(
    relation: dict[str, Any],
    entity_by_id: dict[str, dict[str, Any]],
) -> bool:
    from_entity = entity_by_id.get(str(relation.get("from") or ""))
    to_entity = entity_by_id.get(str(relation.get("to") or ""))
    return (
        from_entity is not None
        and to_entity is not None
        and from_entity.get("type") == "Industry"
        and to_entity.get("type") == "Industry"
    )


def should_drop_relation(
    relation: dict[str, Any],
    entity_by_id: dict[str, dict[str, Any]],
    source_doc: dict[str, Any] | None = None,
    source_id: str = "",
) -> bool:
    if not is_executive_status_source(source_doc, source_id):
        return False

    relation_type = str(relation.get("type") or "")
    if relation_type not in EXECUTIVE_STATUS_COMPANY_RELATION_TYPES:
        return False

    from_entity = entity_by_id.get(str(relation.get("from") or ""))
    to_entity = entity_by_id.get(str(relation.get("to") or ""))
    return (
        from_entity is not None
        and to_entity is not None
        and from_entity.get("type") == "Company"
        and to_entity.get("type") == "Company"
    )


def is_executive_status_source(
    source_doc: dict[str, Any] | None = None,
    source_id: str = "",
) -> bool:
    if not source_doc:
        return source_id.startswith("dart_") and "_executive_status_" in source_id

    dataset = str(source_doc.get("dataset") or "")
    if not dataset and isinstance(source_doc.get("metadata"), dict):
        dataset = str(source_doc["metadata"].get("dataset") or "")
    return dataset == "executive_status"


def normalize_person_company_relation(
    relation: dict[str, Any],
    entity_by_id: dict[str, dict[str, Any]],
) -> None:
    relation_type = str(relation.get("type") or "")
    if relation_type not in PERSON_COMPANY_RELATION_TYPES:
        return

    from_entity = entity_by_id.get(str(relation.get("from") or ""))
    to_entity = entity_by_id.get(str(relation.get("to") or ""))
    if (
        from_entity is None
        or to_entity is None
        or from_entity.get("type") != "Person"
        or to_entity.get("type") != "Company"
    ):
        return

    raw_role = str(relation.get("role_raw") or relation.get("role") or "").strip()
    if not raw_role:
        relation.pop("role", None)
        relation.pop("role_label", None)
        relation.pop("role_raw", None)
        return

    role_code, role_label = normalize_role(raw_role)
    relation["role_raw"] = raw_role
    relation["role"] = role_code
    relation["role_label"] = role_label


def build_evidence_source(source_doc: dict[str, Any]) -> dict[str, str]:
    source_type = str(
        source_doc.get("document_type") or source_doc.get("module_a_type") or ""
    )
    return {
        "date": str(source_doc.get("published_at") or "") if source_type == "dart" else "",
        "evidence_source_id": str(source_doc.get("source_id") or ""),
        "evidence_source_type": source_type,
        "evidence_source_url": str(source_doc.get("url") or ""),
        "evidence_published_at": str(source_doc.get("published_at") or ""),
    }


def ensure_endpoint_entity(
    entity_id: str,
    entity_by_id: dict[str, dict[str, Any]],
    entities: list[dict[str, Any]],
    company_whitelist: CompanyWhitelist | None = None,
) -> None:
    if entity_id in entity_by_id:
        return

    entity_type = infer_entity_type_from_id(entity_id)
    if entity_type is None:
        return

    entity_name = infer_name_from_id(entity_id, entity_type)
    if entity_type == "Company" and (
        company_whitelist is None or not company_whitelist.is_allowed_name(entity_name)
    ):
        return

    entity = {
        "id": entity_id,
        "type": entity_type,
        "name": entity_name,
    }
    entities.append(entity)
    entity_by_id[entity_id] = entity


def filter_allowed_companies(
    entities: list[dict[str, Any]],
    company_whitelist: CompanyWhitelist,
) -> list[dict[str, Any]]:
    return [
        entity
        for entity in entities
        if entity.get("type") != "Company"
        or company_whitelist.is_allowed_name(str(entity.get("name") or ""))
    ]


def infer_entity_type_from_id(entity_id: str) -> str | None:
    if entity_id.startswith("company_"):
        return "Company"
    if entity_id.startswith("person_"):
        return "Person"
    if entity_id.startswith("industry_"):
        return "Industry"
    if entity_id.startswith("business_area_"):
        return "Industry"
    if entity_id.startswith("product_service_"):
        return "ProductService"
    if entity_id.startswith("affiliate_group_"):
        return "AffiliateGroup"
    if entity_id.startswith("event_"):
        return "Event"
    return None


def infer_name_from_id(entity_id: str, entity_type: str) -> str:
    prefixes = {
        "ProductService": "product_service_",
    }
    prefix = (
        LEGACY_BUSINESS_AREA_PREFIX
        if entity_id.startswith(LEGACY_BUSINESS_AREA_PREFIX)
        else prefixes.get(entity_type, f"{entity_type.lower()}_")
    )
    raw_name = entity_id.removeprefix(prefix).replace("_", " ").strip()
    if not raw_name:
        return entity_id
    if re.fullmatch(r"[A-Za-z0-9 .&-]+", raw_name):
        return " ".join(
            part.upper() if len(part) <= 3 else part.capitalize()
            for part in raw_name.split()
        )
    return raw_name
