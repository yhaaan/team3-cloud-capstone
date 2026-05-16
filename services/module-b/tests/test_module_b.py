from __future__ import annotations

import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
ROOT_DIR = SRC_DIR.parent.parent.parent
MODULE_A_DATA_DIR = ROOT_DIR / "services" / "module-a" / "data"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chunking import split_text_into_chunks
from company_whitelist import CompanyWhitelist, ListedCompany
from document_io import iter_input_documents
from graph_pipeline import extract_graph as extract_graph_from_pipeline
from role_normalizer import normalize_graph_roles, normalize_role


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

    def test_chunking_uses_module_a_document(self):
        doc = max(self.docs, key=lambda item: len(item.get("content", "")))
        chunks = split_text_into_chunks(doc, max_chunk_length=120)

        self.assertGreater(len(chunks), 0)
        self.assertEqual(chunks[0]["doc_id"], doc["source_id"])
        self.assertEqual(chunks[0]["title"], doc["title"])

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
            ["company_samsung_electronics", "industry_ai"],
        )
        self.assertEqual(len(normalized["relations"]), 1)
        self.assertEqual(normalized["relations"][0]["type"], "BELONGS_TO")

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


if __name__ == "__main__":
    unittest.main()
