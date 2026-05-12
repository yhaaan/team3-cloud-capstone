from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent.parent
DEFAULT_LISTED_COMPANIES_PATH = ROOT_DIR / "services" / "module-a" / "listed_companies.xlsx"
XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class ListedCompany:
    stock_code: str
    company_name: str
    market: str


class CompanyWhitelist:
    def __init__(self, companies: list[ListedCompany]) -> None:
        self.companies = companies
        self._by_normalized_name = {
            normalize_company_name(company.company_name): company for company in companies
        }
        self._by_stock_code = {
            normalize_stock_code(company.stock_code): company
            for company in companies
            if normalize_stock_code(company.stock_code)
        }

    def find(self, name: str | None = None, stock_code: str | None = None) -> ListedCompany | None:
        if stock_code:
            company = self._by_stock_code.get(normalize_stock_code(stock_code))
            if company is not None:
                return company

        if name:
            return self._by_normalized_name.get(normalize_company_name(name))

        return None

    def is_allowed_name(self, name: str | None) -> bool:
        return self.find(name=name) is not None

    def allowed_companies_for_doc(self, doc: dict[str, Any]) -> list[ListedCompany]:
        candidates: dict[str, ListedCompany] = {}

        for key in ("stock_code", "corp_code"):
            company = self.find(stock_code=str(doc.get(key) or ""))
            if company is not None:
                candidates[company.stock_code] = company

        for key in ("company_name", "corp_name"):
            company = self.find(name=str(doc.get(key) or ""))
            if company is not None:
                candidates[company.stock_code] = company

        haystack = " ".join(
            str(value or "")
            for value in (
                doc.get("title"),
                doc.get("content"),
                doc.get("company_name"),
                doc.get("corp_name"),
            )
        )
        for company in self.companies:
            if company.company_name and company.company_name in haystack:
                candidates[company.stock_code] = company

        return list(candidates.values())


@lru_cache(maxsize=1)
def load_default_company_whitelist() -> CompanyWhitelist:
    return CompanyWhitelist(load_listed_companies(DEFAULT_LISTED_COMPANIES_PATH))


def load_listed_companies(file_path: Path) -> list[ListedCompany]:
    rows = read_xlsx_rows(file_path)
    if not rows:
        return []

    headers = [str(value).strip() for value in rows[0]]
    try:
        stock_code_index = headers.index("stock_code")
        company_name_index = headers.index("company_name")
    except ValueError as exc:
        raise RuntimeError(
            f"listed companies file must include stock_code and company_name headers: {file_path}"
        ) from exc

    market_index = headers.index("market") if "market" in headers else None
    companies: list[ListedCompany] = []

    for row in rows[1:]:
        stock_code = cell_value(row, stock_code_index).zfill(6)
        company_name = cell_value(row, company_name_index)
        market = cell_value(row, market_index) if market_index is not None else ""
        if stock_code and company_name:
            companies.append(ListedCompany(stock_code, company_name, market))

    return companies


def read_xlsx_rows(file_path: Path) -> list[list[str]]:
    with zipfile.ZipFile(file_path) as workbook:
        shared_strings = read_shared_strings(workbook)
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml")

    sheet = ET.fromstring(sheet_xml)
    rows: list[list[str]] = []
    for row in sheet.findall(".//a:sheetData/a:row", XLSX_NS):
        values: list[str] = []
        for cell in row.findall("a:c", XLSX_NS):
            value_node = cell.find("a:v", XLSX_NS)
            value = "" if value_node is None else value_node.text or ""
            if cell.get("t") == "s" and value:
                value = shared_strings[int(value)]
            values.append(value)
        rows.append(values)
    return rows


def read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    return [
        "".join(text.text or "" for text in item.findall(".//a:t", XLSX_NS))
        for item in root.findall("a:si", XLSX_NS)
    ]


def cell_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def normalize_stock_code(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(6) if digits else ""


def normalize_company_name(value: str | None) -> str:
    normalized = str(value or "").casefold()
    return re.sub(r"[\s()\[\]{}.,·ㆍ・&\-_/]+", "", normalized)
