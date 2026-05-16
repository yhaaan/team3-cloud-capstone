from __future__ import annotations

from typing import Any

from company_whitelist import load_default_company_whitelist
from llm_extract_graph import extract_graph_with_openai
from mock_extract_graph import extract_graph as extract_graph_by_rule
from role_normalizer import normalize_graph_roles


def extract_graph(
    doc: dict[str, Any],
    mode: str = "rule",
    allow_fallback: bool = True,
) -> dict[str, Any]:
    company_whitelist = load_default_company_whitelist()

    if mode == "rule":
        return normalize_graph_roles(extract_graph_by_rule(doc), company_whitelist, doc)

    if mode == "openai":
        try:
            return normalize_graph_roles(extract_graph_with_openai(doc), company_whitelist, doc)
        except Exception:
            if not allow_fallback:
                raise
            return normalize_graph_roles(extract_graph_by_rule(doc), company_whitelist, doc)

    raise ValueError(f"지원하지 않는 추출 모드입니다: {mode}")
