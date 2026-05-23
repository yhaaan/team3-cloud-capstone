from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent.parent
DEFAULT_INDUSTRY_TAXONOMY_PATH = ROOT_DIR / "schemas" / "industry_taxonomy.json"


@dataclass(frozen=True)
class IndustryTaxonomyEntry:
    id: str
    name: str
    level: int
    aliases: tuple[str, ...] = ()
    parent_id: str = ""
    related_ids: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


class IndustryTaxonomy:
    def __init__(self, entries: list[IndustryTaxonomyEntry]) -> None:
        self.entries = entries
        self._by_id = {entry.id: entry for entry in entries}
        self._by_normalized_term: dict[str, IndustryTaxonomyEntry] = {}
        for entry in entries:
            for term in (entry.id, entry.name, *entry.aliases, *entry.keywords):
                normalized = normalize_taxonomy_term(term)
                if normalized:
                    self._by_normalized_term.setdefault(normalized, entry)

    def find(
        self,
        entity_id: str | None = None,
        name: str | None = None,
    ) -> IndustryTaxonomyEntry | None:
        for term in (entity_id, name):
            normalized = normalize_taxonomy_term(term)
            if not normalized:
                continue
            entry = self._by_normalized_term.get(normalized)
            if entry is not None:
                return entry
        return None

    def get(self, entry_id: str) -> IndustryTaxonomyEntry | None:
        return self._by_id.get(entry_id)

    def ancestors(self, entry_id: str) -> list[IndustryTaxonomyEntry]:
        ancestors: list[IndustryTaxonomyEntry] = []
        seen: set[str] = set()
        current = self.get(entry_id)
        while current is not None and current.parent_id:
            if current.parent_id in seen:
                break
            seen.add(current.parent_id)
            parent = self.get(current.parent_id)
            if parent is None:
                break
            ancestors.append(parent)
            current = parent
        return ancestors


@lru_cache(maxsize=1)
def load_default_industry_taxonomy() -> IndustryTaxonomy:
    return load_industry_taxonomy(DEFAULT_INDUSTRY_TAXONOMY_PATH)


def load_industry_taxonomy(file_path: Path) -> IndustryTaxonomy:
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    entries = [
        IndustryTaxonomyEntry(
            id=str(item.get("id") or "").strip(),
            name=str(item.get("name") or "").strip(),
            level=int(item.get("level") or 0),
            aliases=tuple(str(value).strip() for value in item.get("aliases", []) if str(value).strip()),
            parent_id=str(item.get("parent_id") or "").strip(),
            related_ids=tuple(str(value).strip() for value in item.get("related_ids", []) if str(value).strip()),
            keywords=tuple(str(value).strip() for value in item.get("keywords", []) if str(value).strip()),
        )
        for item in raw.get("industries", [])
    ]
    entries = [entry for entry in entries if entry.id and entry.name]
    return IndustryTaxonomy(entries)


def normalize_taxonomy_term(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"^industry_", "", text)
    text = re.sub(r"^business_area_", "", text)
    return re.sub(r"[^0-9a-z가-힣]+", "", text)




