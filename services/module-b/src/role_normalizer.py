from __future__ import annotations

import re
from typing import Any


COMPANY_SUFFIX_PATTERN = re.compile(
    r"(주식회사|㈜|\(주\)|주\)|그룹|전자|중공업|하이닉스|바이오로직스|스퀘어|오션|현대|삼성|SK|LG|HD)",
    re.IGNORECASE,
)

ROLE_PATTERNS: list[tuple[str, str, tuple[str, ...]]] = [
    ("CHAIRMAN", "회장", ("회장", "chairman")),
    ("VICE_CHAIRMAN", "부회장", ("부회장", "vice chairman")),
    ("CEO", "대표이사", ("대표이사", "대표", "ceo", "chief executive officer")),
    ("PRESIDENT", "사장", ("사장", "president")),
    ("VICE_PRESIDENT", "부사장", ("부사장", "vice president")),
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

        raw_role = str(entity.get("role") or "").strip()
        if not raw_role:
            entity.pop("role", None)
            continue

        role_code, role_label = normalize_role(raw_role)
        entity["role_raw"] = raw_role
        entity["role"] = role_code
        entity["role_label"] = role_label

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
