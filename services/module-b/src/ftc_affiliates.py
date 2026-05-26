from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from company_whitelist import CompanyWhitelist, ListedCompany, load_default_company_whitelist, normalize_company_name, normalize_stock_code
from role_normalizer import build_company_id


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent.parent
DEFAULT_FTC_AFFILIATES_PATH = ROOT_DIR / "docs" / "ftc_affiliates.jsonl"
FTC_SOURCE_NAME = "ftc_affiliates"


@dataclass(frozen=True)
class FtcAffiliateRecord:
    presentn_year: str
    unity_group_code: str
    unity_group_name: str
    company_name: str
    jurirno: str
    bizrno: str
    representative_name: str
    founded_on: str
    joined_on: str


@dataclass(frozen=True)
class MatchedFtcAffiliate:
    record: FtcAffiliateRecord
    company: ListedCompany


@dataclass(frozen=True)
class FtcAffiliateMatchResult:
    matched: list[MatchedFtcAffiliate]
    unmatched: list[FtcAffiliateRecord]


COMPANY_LEGAL_SUFFIX_PATTERN = re.compile(r"\(주\)|㈜|주식회사|\s+")
ID_TOKEN_PATTERN = re.compile(r"[^0-9A-Za-z가-힣]+")
KOREANIZED_ABBREVIATION_ALIASES = {
    "비지에프": "BGF",
    "디비": "DB",
    "디엘": "DL",
    "에이치디": "HD",
    "에이치엘": "HL",
    "케이지": "KG",
    "엔에이치": "NH",
    "씨제이": "CJ",
    "에스케이": "SK",
    "에이치엠엠": "HMM",
    "엘에스": "LS",
    "엘엑스": "LX",
    "엘지": "LG",
    "지에스": "GS",
    "케이씨씨": "KCC",
    "케이티": "KT",
    "에이치에스": "HS",
}
FTC_COMPANY_NAME_ALIASES = {
    "롯데칠성음료": "롯데칠성",
    "KT스카이라이프": "스카이라이프",
    "KT아이에스": "KTis",
    "현대해상화재보험": "현대해상",
}


def load_ftc_affiliate_records(file_path: Path = DEFAULT_FTC_AFFILIATES_PATH) -> list[FtcAffiliateRecord]:
    records: list[FtcAffiliateRecord] = []
    with file_path.open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            item = json.loads(stripped)
            records.append(
                FtcAffiliateRecord(
                    presentn_year=str(item.get("presentnYear") or "").strip(),
                    unity_group_code=str(item.get("unityGrupCode") or "").strip(),
                    unity_group_name=str(item.get("unityGrupNm") or "").strip(),
                    company_name=str(item.get("entrprsNm") or "").strip(),
                    jurirno=str(item.get("jurirno") or "").strip(),
                    bizrno=str(item.get("bizrno") or "").strip(),
                    representative_name=str(item.get("rprsntvNm") or "").strip(),
                    founded_on=normalize_yyyymmdd(item.get("fondDe")),
                    joined_on=normalize_yyyymmdd(item.get("grinil")),
                )
            )
    return records


def match_ftc_affiliates_to_listed_companies(
    records: list[FtcAffiliateRecord],
    company_whitelist: CompanyWhitelist | None = None,
) -> FtcAffiliateMatchResult:
    whitelist = company_whitelist or load_default_company_whitelist()
    companies_by_clean_name = {
        normalize_ftc_company_name(company.company_name): company
        for company in whitelist.companies
    }

    matched: list[MatchedFtcAffiliate] = []
    unmatched: list[FtcAffiliateRecord] = []
    for record in records:
        company = companies_by_clean_name.get(normalize_ftc_company_name(record.company_name))
        if company is None:
            unmatched.append(record)
            continue
        matched.append(MatchedFtcAffiliate(record, company))
    return FtcAffiliateMatchResult(matched=matched, unmatched=unmatched)


def build_ftc_affiliates_graph(
    file_path: Path = DEFAULT_FTC_AFFILIATES_PATH,
    company_whitelist: CompanyWhitelist | None = None,
) -> dict[str, Any]:
    records = load_ftc_affiliate_records(file_path)
    match_result = match_ftc_affiliates_to_listed_companies(records, company_whitelist)
    if match_result.unmatched:
        unmatched_names = ", ".join(record.company_name for record in match_result.unmatched[:10])
        raise RuntimeError(
            f"FTC affiliate rows failed listed-company matching: {len(match_result.unmatched)}; {unmatched_names}"
        )

    entities_by_id: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    seen_relations: set[tuple[str, str, str]] = set()

    for matched in match_result.matched:
        record = matched.record
        company = matched.company
        company_id = build_company_id(company.stock_code)
        group_id = build_affiliate_group_id(record.unity_group_name)

        entities_by_id.setdefault(
            company_id,
            {
                "id": company_id,
                "type": "Company",
                "name": company.company_name,
                "stock_code": normalize_stock_code(company.stock_code),
            },
        )

        group_entity = entities_by_id.setdefault(
            group_id,
            {
                "id": group_id,
                "type": "AffiliateGroup",
                "name": record.unity_group_name,
                "presentn_year": record.presentn_year,
                "source": FTC_SOURCE_NAME,
            },
        )
        if record.unity_group_code and not group_entity.get("unity_group_code"):
            group_entity["unity_group_code"] = record.unity_group_code

        relation_key = ("MEMBER_OF", company_id, group_id)
        if relation_key in seen_relations:
            continue
        seen_relations.add(relation_key)
        relations.append(
            compact_dict(
                {
                    "type": "MEMBER_OF",
                    "from": company_id,
                    "to": group_id,
                    "evidence": f"FTC {record.presentn_year}: {company.company_name} is listed as a member of {record.unity_group_name}.",
                    "presentn_year": record.presentn_year,
                    "jurirno": record.jurirno,
                    "bizrno": record.bizrno,
                    "representative_name": record.representative_name,
                    "founded_on": record.founded_on,
                    "joined_on": record.joined_on,
                    "source": FTC_SOURCE_NAME,
                }
            )
        )

    return {
        "source_id": build_ftc_source_id(records),
        "entities": list(entities_by_id.values()),
        "relations": relations,
    }


def normalize_ftc_company_name(value: str | None) -> str:
    cleaned = COMPANY_LEGAL_SUFFIX_PATTERN.sub("", str(value or ""))
    cleaned = apply_company_name_aliases(cleaned)
    return normalize_company_name(cleaned)


def apply_company_name_aliases(value: str) -> str:
    cleaned = value
    for koreanized, abbreviation in KOREANIZED_ABBREVIATION_ALIASES.items():
        cleaned = cleaned.replace(koreanized, abbreviation)

    if cleaned.startswith("현대자동차"):
        cleaned = "현대차" + cleaned.removeprefix("현대자동차")
    if cleaned == "한국항공우주산업":
        cleaned = "한국항공우주"
    cleaned = FTC_COMPANY_NAME_ALIASES.get(cleaned, cleaned)
    if cleaned.endswith("해상보험"):
        cleaned = cleaned.removesuffix("해상보험")
    elif cleaned.endswith("생명보험") or cleaned.endswith("손해보험") or cleaned.endswith("화재보험"):
        cleaned = cleaned.removesuffix("보험")
    return cleaned


def build_affiliate_group_id(group_name: str) -> str:
    slug = ID_TOKEN_PATTERN.sub("_", group_name.strip()).strip("_").lower()
    return f"affiliate_group_{slug or 'unknown'}"


def build_ftc_source_id(records: list[FtcAffiliateRecord]) -> str:
    years = sorted({record.presentn_year for record in records if record.presentn_year})
    return f"ftc_affiliates_{years[-1]}" if years else "ftc_affiliates"


def normalize_yyyymmdd(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) == 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return str(value or "").strip()


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in [None, ""]}
