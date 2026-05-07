from __future__ import annotations

import re
from typing import Any


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


def normalize_graph_roles(graph_data: dict[str, Any]) -> dict[str, Any]:
    for entity in graph_data.get("entities", []):
        if entity.get("type") != "Person":
            continue

        raw_role = str(entity.get("role_raw") or entity.get("role") or "").strip()
        if not raw_role:
            entity.pop("role", None)
            continue

        role_code, role_label = normalize_role(raw_role)
        entity["role_raw"] = raw_role
        entity["role"] = role_code
        entity["role_label"] = role_label

    graph_data["entities"] = deduplicate_entities_by_id(graph_data.get("entities", []))
    graph_data["relations"] = repair_relations(
        graph_data.get("relations", []),
        graph_data["entities"],
    )
    return graph_data


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

        ensure_endpoint_entity(from_id, entity_by_id, entities)
        ensure_endpoint_entity(to_id, entity_by_id, entities)

        if from_id not in entity_by_id or to_id not in entity_by_id:
            continue

        relation_key = (relation.get("type", ""), from_id, to_id, evidence)
        if relation_key in seen:
            continue
        seen.add(relation_key)

        repaired_relation = dict(relation)
        repaired_relation["from"] = from_id
        repaired_relation["to"] = to_id
        repaired_relation["evidence"] = evidence
        repaired.append(repaired_relation)

    return repaired


def ensure_endpoint_entity(
    entity_id: str,
    entity_by_id: dict[str, dict[str, Any]],
    entities: list[dict[str, Any]],
) -> None:
    if entity_id in entity_by_id:
        return

    entity_type = infer_entity_type_from_id(entity_id)
    if entity_type is None:
        return

    entity = {
        "id": entity_id,
        "type": entity_type,
        "name": infer_name_from_id(entity_id, entity_type),
    }
    entities.append(entity)
    entity_by_id[entity_id] = entity


def infer_entity_type_from_id(entity_id: str) -> str | None:
    if entity_id.startswith("company_"):
        return "Company"
    if entity_id.startswith("person_"):
        return "Person"
    if entity_id.startswith("industry_"):
        return "Industry"
    if entity_id.startswith("event_"):
        return "Event"
    return None


def infer_name_from_id(entity_id: str, entity_type: str) -> str:
    prefix = f"{entity_type.lower()}_"
    raw_name = entity_id.removeprefix(prefix).replace("_", " ").strip()
    if not raw_name:
        return entity_id
    if re.fullmatch(r"[A-Za-z0-9 .&-]+", raw_name):
        return " ".join(
            part.upper() if len(part) <= 3 else part.capitalize()
            for part in raw_name.split()
        )
    return raw_name
