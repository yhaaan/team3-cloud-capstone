from __future__ import annotations

import sys
import unittest
from pathlib import Path

from jsonschema import validate


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
ROOT_DIR = SRC_DIR.parent.parent.parent
MODULE_A_DATA_DIR = ROOT_DIR / "services" / "module-a" / "data"
GRAPH_SCHEMA_PATH = ROOT_DIR / "schemas" / "graph_schema.json"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chunking import split_text_into_chunks
from company_whitelist import CompanyWhitelist, ListedCompany
from document_io import iter_input_documents, normalize_document
from graph_pipeline import extract_graph as extract_graph_from_pipeline
from load_chroma import build_chunk_payloads
from role_normalizer import normalize_graph_roles, normalize_role
from run_to_neo4j import filter_documents_by_dataset


class ModuleBPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = iter_input_documents(MODULE_A_DATA_DIR)
        cls.news_docs = [doc for doc in cls.docs if doc.get("module_a_type") == "news"]
        cls.dart_docs = [doc for doc in cls.docs if doc.get("module_a_type") == "dart"]

    def test_module_a_data_directory_loading(self):
        self.assertGreater(len(self.docs), 0)
        self.assertGreater(len(self.news_docs), 0)
        self.assertGreater(len(self.dart_docs), 0)

    def test_module_a_news_document_mapping(self):
        doc = self.news_docs[0]

        self.assertTrue(doc["source_id"])
        self.assertTrue(doc["title"])
        self.assertTrue(doc["content"])
        self.assertTrue(doc["published_at"])
        self.assertTrue(doc["url"])
        self.assertEqual(doc["module_a_type"], "news")

    def test_module_a_dart_document_mapping(self):
        doc = self.dart_docs[0]

        self.assertTrue(doc["source_id"])
        self.assertTrue(doc["title"])
        self.assertTrue(doc["content"])
        self.assertEqual(doc["source"], "dart")
        self.assertEqual(doc["module_a_type"], "dart")

    def test_module_a_major_issue_detail_mapping_preserves_detail_fields(self):
        doc = normalize_document(
            {
                "doc_id": "dart_001_major_issue_report_detail_20260326000880",
                "company_name": "Example Corp",
                "stock_code": "000001",
                "corp_code": "001",
                "source": "dart",
                "dataset": "major_issue_report_detail",
                "event_type": "merger",
                "report_nm": "Major Issue Report",
                "rcept_no": "20260326000880",
                "rcept_dt": "20260326",
                "plain_text": "Example Corp will merge with Target Corp.",
                "text_blocks": [],
                "counterparty_candidates": ["Target Corp"],
                "amount_candidates": ["1000000"],
                "ratio_candidates": ["1:0.5"],
                "date_candidates": ["2026-03-26"],
                "relation_relevance_score": 0.9,
                "is_relation_candidate": True,
            },
            Path("major_issue_report_details/20260326000880.json"),
        )

        self.assertEqual(doc["title"], "Example Corp Major Issue Report")
        self.assertEqual(doc["content"], "Example Corp will merge with Target Corp.")
        self.assertEqual(doc["published_at"], "2026-03-26")
        self.assertEqual(doc["metadata"]["event_type"], "merger")
        self.assertEqual(doc["metadata"]["counterparty_candidates"], ["Target Corp"])
        self.assertEqual(doc["metadata"]["amount_candidates"], ["1000000"])
        self.assertEqual(doc["metadata"]["ratio_candidates"], ["1:0.5"])
        self.assertEqual(doc["metadata"]["date_candidates"], ["2026-03-26"])

    def test_module_a_consolidated_subsidiary_mapping_preserves_subsidiaries(self):
        doc = normalize_document(
            {
                "doc_id": "dart_001_consolidated_subsidiary_status_20260318000532",
                "company_name": "Example Corp",
                "stock_code": "000001",
                "corp_code": "001",
                "source": "dart",
                "dataset": "consolidated_subsidiary_status",
                "dataset_label": "Consolidated subsidiaries",
                "report_nm": "Annual Report",
                "rcept_no": "20260318000532",
                "rcept_dt": "20260318",
                "record_count": 1,
                "meaningful_record_count": 1,
                "normalized_records": [
                    {
                        "raw_company_name": "Target Corp",
                        "matched_company_name": "Target Corp",
                        "matched_stock_code": "000002",
                    }
                ],
                "text_blocks": ["Example Corp has Target Corp as a consolidated subsidiary."],
                "listed_subsidiaries": ["Target Corp"],
                "subsidiary_candidates": ["Target Corp"],
                "mentioned_entities": ["Target Corp"],
                "relation_relevance_score": 0.8,
                "is_relation_candidate": True,
            },
            Path("consolidated_subsidiary_status/latest.json"),
        )

        self.assertEqual(doc["title"], "Example Corp Annual Report")
        self.assertEqual(
            doc["content"],
            "Example Corp has Target Corp as a consolidated subsidiary.",
        )
        self.assertEqual(doc["metadata"]["listed_subsidiaries"], ["Target Corp"])
        self.assertEqual(doc["metadata"]["subsidiary_candidates"], ["Target Corp"])

    def test_filter_documents_by_dataset_keeps_only_requested_datasets(self):
        documents = [
            {"source_id": "news_001", "document_type": "news"},
            {"source_id": "dart_001", "dataset": "major_issue_report_detail"},
            {"source_id": "dart_002", "dataset": "consolidated_subsidiary_status"},
            {"source_id": "dart_003", "dataset": "executive_status"},
        ]

        filtered = filter_documents_by_dataset(
            documents,
            ["major_issue_report_detail", "consolidated_subsidiary_status"],
        )

        self.assertEqual(
            [doc["source_id"] for doc in filtered],
            ["dart_001", "dart_002"],
        )

    def test_chunking_uses_module_a_document(self):
        doc = max(self.docs, key=lambda item: len(item.get("content", "")))
        chunks = split_text_into_chunks(doc, max_chunk_length=120)

        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[0]["doc_id"], doc["source_id"])
        self.assertEqual(chunks[0]["title"], doc["title"])

    def test_chroma_metadata_preserves_company_and_dataset_context(self):
        doc = {
            "source_id": "dart_005930_business_segments_20260310002820",
            "document_type": "dart",
            "title": "Samsung Electronics business segments",
            "content": "Samsung Electronics operates semiconductor and smartphone businesses.",
            "source": "dart",
            "published_at": "2026-03-10",
            "url": "https://example.com",
            "company_name": "Samsung Electronics",
            "stock_code": "005930",
            "corp_code": "00126380",
            "dataset": "business_segments",
            "dataset_label": "Business segments",
            "metadata": {},
        }

        _, _, metadatas = build_chunk_payloads(doc)

        self.assertGreater(len(metadatas), 0)
        self.assertEqual(metadatas[0]["dataset"], "business_segments")
        self.assertEqual(metadatas[0]["company_name"], "Samsung Electronics")
        self.assertEqual(metadatas[0]["stock_code"], "005930")
        self.assertEqual(metadatas[0]["corp_code"], "00126380")

    def test_graph_pipeline_rule_mode_uses_module_a_document(self):
        doc = self.docs[0]
        graph = extract_graph_from_pipeline(doc, mode="rule")

        self.assertEqual(graph["source_id"], doc["source_id"])
        self.assertIn("entities", graph)
        self.assertIn("relations", graph)

    def test_role_normalization_preserves_raw_and_standardizes_role(self):
        role, label = normalize_role("삼성전자 회장")

        self.assertEqual(role, "CHAIRMAN")
        self.assertEqual(label, "회장")

        graph = {
            "source_id": "test",
            "entities": [
                {
                    "id": "person_test",
                    "type": "Person",
                    "name": "홍길동",
                    "role": "삼성전자 회장",
                }
            ],
            "relations": [],
        }

        normalized = normalize_graph_roles(graph)
        person = normalized["entities"][0]

        self.assertEqual(person["role"], "CHAIRMAN")
        self.assertEqual(person["role_label"], "회장")
        self.assertEqual(person["role_raw"], "삼성전자 회장")

    def test_role_normalization_prefers_specific_role_aliases(self):
        self.assertEqual(normalize_role("삼성전자 부회장"), ("VICE_CHAIRMAN", "부회장"))
        self.assertEqual(normalize_role("부사장"), ("VICE_PRESIDENT", "부사장"))

    def test_role_normalization_is_idempotent_for_exported_graphs(self):
        graph = {
            "source_id": "test",
            "entities": [
                {
                    "id": "person_test",
                    "type": "Person",
                    "name": "홍길동",
                    "role": "VICE_CHAIRMAN",
                    "role_raw": "부회장",
                    "role_label": "부회장",
                }
            ],
            "relations": [],
        }

        normalized = normalize_graph_roles(graph)
        person = normalized["entities"][0]

        self.assertEqual(person["role"], "VICE_CHAIRMAN")
        self.assertEqual(person["role_label"], "부회장")
        self.assertEqual(person["role_raw"], "부회장")

    def test_graph_normalization_deduplicates_and_repairs_relations(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "company_example_inc", "type": "Company", "name": "Example Inc."},
                {"id": "company_example_inc", "type": "Company", "name": "Example Inc"},
            ],
            "relations": [
                {
                    "type": "BELONGS_TO",
                    "from": "company_example_inc",
                    "to": "industry_ai",
                    "evidence": "Example Inc.는 AI 산업에 속한다.",
                },
                {
                    "type": "AFFILIATED_WITH",
                    "from": "person_missing",
                    "to": "",
                    "evidence": "endpoint가 비어 있는 관계는 제거한다.",
                },
            ],
        }

        normalized = normalize_graph_roles(graph)

        self.assertEqual(
            [entity["id"] for entity in normalized["entities"]].count("company_example_inc"),
            1,
        )
        self.assertIn(
            {"id": "industry_ai", "type": "Industry", "name": "AI"},
            normalized["entities"],
        )
        self.assertEqual(len(normalized["relations"]), 1)
        self.assertEqual(normalized["relations"][0]["to"], "industry_ai")

    def test_graph_normalization_filters_unlisted_companies_and_relations(self):
        whitelist = CompanyWhitelist(
            [ListedCompany("005930", "Samsung Electronics", "KOSPI")]
        )
        graph = {
            "source_id": "test",
            "entities": [
                {
                    "id": "company_samsung_electronics",
                    "type": "Company",
                    "name": "Samsung Electronics",
                },
                {"id": "company_unlisted", "type": "Company", "name": "Unlisted Co"},
                {"id": "industry_ai", "type": "Industry", "name": "AI"},
            ],
            "relations": [
                {
                    "type": "BELONGS_TO",
                    "from": "company_samsung_electronics",
                    "to": "industry_ai",
                    "evidence": "Samsung Electronics belongs to AI.",
                },
                {
                    "type": "INVESTS_IN",
                    "from": "company_samsung_electronics",
                    "to": "company_unlisted",
                    "evidence": "Samsung Electronics invested in Unlisted Co.",
                },
            ],
        }

        normalized = normalize_graph_roles(graph, whitelist)

        self.assertEqual(
            [entity["id"] for entity in normalized["entities"]],
            ["company_005930", "industry_ai"],
        )
        self.assertEqual(normalized["entities"][0]["stock_code"], "005930")
        self.assertEqual(len(normalized["relations"]), 1)
        self.assertEqual(normalized["relations"][0]["type"], "BELONGS_TO")
        self.assertEqual(normalized["relations"][0]["from"], "company_005930")

    def test_graph_normalization_canonicalizes_company_id_by_stock_code(self):
        whitelist = CompanyWhitelist(
            [ListedCompany("375500", "DL이앤씨", "KOSPI")]
        )
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "company_dl_e_c", "type": "Company", "name": "DL이앤씨"},
                {"id": "company_DL이앤씨", "type": "Company", "name": "DL이앤씨"},
                {"id": "industry_construction", "type": "Industry", "name": "Construction"},
            ],
            "relations": [
                {
                    "type": "BELONGS_TO",
                    "from": "company_dl_e_c",
                    "to": "industry_construction",
                    "evidence": "DL이앤씨 is a construction company.",
                },
                {
                    "type": "BELONGS_TO",
                    "from": "company_DL이앤씨",
                    "to": "industry_construction",
                    "evidence": "DL이앤씨 is a construction company.",
                },
            ],
        }

        normalized = normalize_graph_roles(graph, whitelist)

        companies = [entity for entity in normalized["entities"] if entity["type"] == "Company"]
        self.assertEqual(companies, [{"id": "company_375500", "type": "Company", "name": "DL이앤씨", "stock_code": "375500"}])
        self.assertEqual(len(normalized["relations"]), 1)
        self.assertEqual(normalized["relations"][0]["from"], "company_375500")

    def test_graph_normalization_adds_evidence_source_fields(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "company_example", "type": "Company", "name": "Example"},
                {"id": "industry_ai", "type": "Industry", "name": "AI"},
            ],
            "relations": [
                {
                    "type": "BELONGS_TO",
                    "from": "company_example",
                    "to": "industry_ai",
                    "evidence": "Example belongs to AI.",
                },
            ],
        }
        source_doc = {
            "source_id": "news_001",
            "document_type": "news",
            "url": "https://example.com/news/1",
            "published_at": "2026-05-12T10:00:00+09:00",
        }

        normalized = normalize_graph_roles(graph, source_doc=source_doc)
        relation = normalized["relations"][0]

        self.assertEqual(relation["evidence_source_id"], "news_001")
        self.assertEqual(relation["evidence_source_type"], "news")
        self.assertEqual(relation["evidence_source_url"], "https://example.com/news/1")
        self.assertEqual(relation["evidence_published_at"], "2026-05-12T10:00:00+09:00")
        self.assertEqual(relation["date"], "")

    def test_graph_normalization_adds_relation_date_for_dart_source(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "company_example", "type": "Company", "name": "Example"},
                {"id": "industry_ai", "type": "Industry", "name": "AI"},
            ],
            "relations": [
                {
                    "type": "BELONGS_TO",
                    "from": "company_example",
                    "to": "industry_ai",
                    "evidence": "Example belongs to AI.",
                },
            ],
        }
        source_doc = {
            "source_id": "dart_001",
            "document_type": "dart",
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260320001032",
            "published_at": "2026-03-20",
        }

        normalized = normalize_graph_roles(graph, source_doc=source_doc)

        self.assertEqual(normalized["relations"][0]["date"], "2026-03-20")

    def test_graph_schema_accepts_business_inference_entities(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "company_005930", "type": "Company", "name": "Samsung Electronics", "stock_code": "005930"},
                {"id": "business_area_hbm", "type": "BusinessArea", "name": "HBM"},
                {"id": "product_service_dram", "type": "ProductService", "name": "DRAM"},
                {"id": "industry_semiconductor", "type": "Industry", "name": "Semiconductor"},
            ],
            "relations": [
                {
                    "type": "OPERATES_IN",
                    "from": "company_005930",
                    "to": "business_area_hbm",
                    "evidence": "Samsung Electronics operates in HBM.",
                },
                {
                    "type": "PRODUCES",
                    "from": "company_005930",
                    "to": "product_service_dram",
                    "evidence": "Samsung Electronics produces DRAM.",
                },
                {
                    "type": "PART_OF",
                    "from": "product_service_dram",
                    "to": "business_area_hbm",
                    "evidence": "DRAM is part of the HBM business area.",
                },
            ],
        }

        validate(instance=graph, schema=__import__("json").loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
