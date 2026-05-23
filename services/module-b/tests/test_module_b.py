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
from ftc_affiliates import build_ftc_affiliates_graph, load_ftc_affiliate_records, match_ftc_affiliates_to_listed_companies, normalize_ftc_company_name
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

    def legacy_role_normalization_preserves_raw_and_standardizes_role(self):
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

        normalized = normalize_graph_roles(
            graph,
            source_doc={"document_type": "dart", "dataset": "executive_status"},
        )
        person = normalized["entities"][0]

        self.assertEqual(person["role"], "CHAIRMAN")
        self.assertEqual(person["role_label"], "회장")
        self.assertEqual(person["role_raw"], "삼성전자 회장")

    def test_role_normalization_prefers_specific_role_aliases(self):
        self.assertEqual(normalize_role("삼성전자 부회장"), ("VICE_CHAIRMAN", "부회장"))
        self.assertEqual(normalize_role("부사장"), ("VICE_PRESIDENT", "부사장"))

    def test_person_role_fields_move_to_person_company_relation(self):
        graph = {
            "source_id": "test",
            "entities": [
                {
                    "id": "person_shared",
                    "type": "Person",
                    "name": "Shared Person",
                    "role": "CEO",
                    "role_raw": "CEO",
                    "role_label": "CEO",
                    "responsibility": "Global role",
                },
                {"id": "company_000001", "type": "Company", "name": "Alpha"},
            ],
            "relations": [
                {
                    "type": "AFFILIATED_WITH",
                    "from": "person_shared",
                    "to": "company_000001",
                    "evidence": "Shared Person is affiliated with Alpha.",
                    "role_raw": "chairman",
                    "board_role": "inside director",
                    "responsibility": "Alpha chair",
                }
            ],
        }

        normalized = normalize_graph_roles(
            graph,
            source_doc={"document_type": "dart", "dataset": "executive_status"},
        )
        person = next(entity for entity in normalized["entities"] if entity["type"] == "Person")
        relation = normalized["relations"][0]

        self.assertNotIn("role", person)
        self.assertNotIn("role_raw", person)
        self.assertNotIn("role_label", person)
        self.assertNotIn("responsibility", person)
        self.assertEqual(relation["role"], "CHAIRMAN")
        self.assertEqual(relation["role_raw"], "chairman")
        self.assertEqual(relation["role_label"], "회장")
        self.assertEqual(relation["board_role"], "inside director")
        self.assertEqual(relation["responsibility"], "Alpha chair")

    def test_executive_status_drops_company_company_investment_relations(self):
        graph = {
            "source_id": "dart_000001_executive_status_2025_11011",
            "entities": [
                {"id": "company_000001", "type": "Company", "name": "Alpha"},
                {"id": "company_000002", "type": "Company", "name": "Beta"},
            ],
            "relations": [
                {
                    "type": "INVESTS_IN",
                    "from": "company_000001",
                    "to": "company_000002",
                    "evidence": "An executive career mentions Beta.",
                }
            ],
        }

        normalized = normalize_graph_roles(
            graph,
            source_doc={"document_type": "dart", "dataset": "executive_status"},
        )

        self.assertEqual(normalized["relations"], [])

    def legacy_role_normalization_is_idempotent_for_exported_graphs(self):
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

        normalized = normalize_graph_roles(
            graph,
            source_doc={"document_type": "dart", "dataset": "executive_status"},
        )
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

        entity_ids = {entity["id"] for entity in normalized["entities"]}
        self.assertIn("company_005930", entity_ids)
        self.assertIn("industry_ai", entity_ids)
        self.assertNotIn("company_unlisted", entity_ids)
        self.assertEqual(normalized["entities"][0]["stock_code"], "005930")
        self.assertIn(
            {
                "type": "BELONGS_TO",
                "from": "company_005930",
                "to": "industry_ai",
                "evidence": "Samsung Electronics belongs to AI.",
            },
            normalized["relations"],
        )

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
        self.assertIn(
            {
                "type": "BELONGS_TO",
                "from": "company_375500",
                "to": "industry_construction_infrastructure",
                "evidence": "DL이앤씨 is a construction company.",
            },
            normalized["relations"],
        )

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

    def test_graph_normalization_canonicalizes_industry_aliases(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "company_005930", "type": "Company", "name": "Samsung Electronics"},
                {"id": "industry_robot", "type": "Industry", "name": "로봇"},
                {"id": "industry_robotics_alias", "type": "Industry", "name": "robotics"},
            ],
            "relations": [
                {
                    "type": "BELONGS_TO",
                    "from": "company_005930",
                    "to": "industry_robot",
                    "evidence": "Samsung Electronics has a robot business.",
                },
                {
                    "type": "RELATED_TO",
                    "from": "industry_robotics_alias",
                    "to": "industry_ai",
                    "evidence": "Robotics and AI are related.",
                },
            ],
        }

        normalized = normalize_graph_roles(graph)
        industry_entities = [entity for entity in normalized["entities"] if entity["id"] == "industry_robotics"]

        self.assertEqual(len(industry_entities), 1)
        self.assertEqual(industry_entities[0]["name"], "로보틱스")
        self.assertIn(
            {
                "type": "BELONGS_TO",
                "from": "company_005930",
                "to": "industry_robotics",
                "evidence": "Samsung Electronics has a robot business.",
            },
            normalized["relations"],
        )

    def test_graph_normalization_adds_taxonomy_hierarchy(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "industry_high_bandwidth_memory", "type": "Industry", "name": "High Bandwidth Memory"},
            ],
            "relations": [],
        }

        normalized = normalize_graph_roles(graph)
        entity_ids = {entity["id"] for entity in normalized["entities"]}

        self.assertIn("industry_hbm", entity_ids)
        self.assertIn("industry_memory_semiconductor", entity_ids)
        self.assertIn("industry_semiconductor", entity_ids)
        self.assertIn(
            {
                "type": "PART_OF",
                "from": "industry_hbm",
                "to": "industry_memory_semiconductor",
                "evidence": "Industry taxonomy: 고대역폭메모리 is part of 메모리반도체.",
            },
            normalized["relations"],
        )
        self.assertIn(
            {
                "type": "PART_OF",
                "from": "industry_memory_semiconductor",
                "to": "industry_semiconductor",
                "evidence": "Industry taxonomy: 메모리반도체 is part of 반도체.",
            },
            normalized["relations"],
        )

    def test_ftc_affiliate_records_match_listed_companies(self):
        records = load_ftc_affiliate_records(ROOT_DIR / "docs" / "ftc_affiliates.jsonl")
        match_result = match_ftc_affiliates_to_listed_companies(records)

        self.assertEqual(len(records), 221)
        self.assertEqual(len(match_result.matched), 221)
        self.assertEqual(match_result.unmatched, [])
        self.assertEqual(normalize_ftc_company_name("삼성전자(주)"), normalize_ftc_company_name("삼성전자"))

    def test_ftc_affiliates_graph_builds_group_memberships(self):
        graph = build_ftc_affiliates_graph(ROOT_DIR / "docs" / "ftc_affiliates.jsonl")
        schema = __import__("json").loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8"))
        validate(instance=graph, schema=schema)

        affiliate_groups = [entity for entity in graph["entities"] if entity["type"] == "AffiliateGroup"]
        company_entities = [entity for entity in graph["entities"] if entity["type"] == "Company"]
        member_relations = [relation for relation in graph["relations"] if relation["type"] == "MEMBER_OF"]

        self.assertEqual(graph["source_id"], "ftc_affiliates_202505")
        self.assertEqual(len(affiliate_groups), 64)
        self.assertEqual(len(company_entities), 221)
        self.assertEqual(len(member_relations), 221)
        self.assertIn(
            {"id": "affiliate_group_삼성", "type": "AffiliateGroup", "name": "삼성", "presentn_year": "202505", "source": "ftc_affiliates"},
            affiliate_groups,
        )
        self.assertIn(
            {
                "type": "MEMBER_OF",
                "from": "company_005930",
                "to": "affiliate_group_삼성",
                "evidence": "FTC 202505: 삼성전자 is listed as a member of 삼성.",
                "presentn_year": "202505",
                "jurirno": "1301110006246",
                "bizrno": "1248100998",
                "representative_name": "전영현",
                "founded_on": "1969-01-13",
                "joined_on": "1969-01-13",
                "source": "ftc_affiliates",
            },
            member_relations,
        )

    def test_graph_schema_accepts_industry_taxonomy_entities(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "company_005930", "type": "Company", "name": "Samsung Electronics", "stock_code": "005930"},
                {"id": "industry_hbm", "type": "Industry", "name": "HBM"},
                {"id": "product_service_dram", "type": "ProductService", "name": "DRAM"},
                {"id": "industry_semiconductor", "type": "Industry", "name": "Semiconductor"},
                {"id": "industry_display", "type": "Industry", "name": "Display"},
            ],
            "relations": [
                {
                    "type": "BELONGS_TO",
                    "from": "company_005930",
                    "to": "industry_hbm",
                    "evidence": "Samsung Electronics belongs to HBM.",
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
                    "to": "industry_semiconductor",
                    "evidence": "DRAM is part of the semiconductor industry.",
                },
                {
                    "type": "PART_OF",
                    "from": "industry_hbm",
                    "to": "industry_semiconductor",
                    "evidence": "HBM is part of the semiconductor industry.",
                },
                {
                    "type": "RELATED_TO",
                    "from": "industry_semiconductor",
                    "to": "industry_display",
                    "evidence": "Semiconductor and display industries are related.",
                },
            ],
        }

        validate(instance=graph, schema=__import__("json").loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8")))

    def test_graph_normalization_converts_business_area_to_industry(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "company_005930", "type": "Company", "name": "Samsung Electronics"},
                {"id": "business_area_hbm", "type": "BusinessArea", "name": "HBM"},
                {"id": "industry_semiconductor", "type": "Industry", "name": "Semiconductor"},
                {"id": "product_service_dram", "type": "ProductService", "name": "DRAM"},
            ],
            "relations": [
                {
                    "type": "OPERATES_IN",
                    "from": "company_005930",
                    "to": "business_area_hbm",
                    "evidence": "Samsung Electronics operates in HBM.",
                },
                {
                    "type": "PART_OF",
                    "from": "business_area_hbm",
                    "to": "industry_semiconductor",
                    "evidence": "HBM is part of semiconductor.",
                },
                {
                    "type": "PART_OF",
                    "from": "product_service_dram",
                    "to": "business_area_hbm",
                    "evidence": "DRAM is part of HBM.",
                },
            ],
        }

        normalized = normalize_graph_roles(graph)

        self.assertIn(
            {"id": "industry_hbm", "type": "Industry", "name": "HBM"},
            normalized["entities"],
        )
        self.assertNotIn("BusinessArea", {entity["type"] for entity in normalized["entities"]})
        self.assertIn(
            {
                "type": "BELONGS_TO",
                "from": "company_005930",
                "to": "industry_hbm",
                "evidence": "Samsung Electronics operates in HBM.",
            },
            normalized["relations"],
        )
        self.assertIn(
            {
                "type": "PART_OF",
                "from": "industry_hbm",
                "to": "industry_semiconductor",
                "evidence": "HBM is part of semiconductor.",
            },
            normalized["relations"],
        )
        self.assertIn(
            {
                "type": "PART_OF",
                "from": "product_service_dram",
                "to": "industry_hbm",
                "evidence": "DRAM is part of HBM.",
            },
            normalized["relations"],
        )
        validate(instance=normalized, schema=__import__("json").loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8")))

    def test_graph_normalization_prefers_part_of_over_related_to_for_industries(self):
        graph = {
            "source_id": "test",
            "entities": [
                {"id": "industry_cloud_service", "type": "Industry", "name": "Cloud Service"},
                {"id": "industry_it", "type": "Industry", "name": "IT"},
            ],
            "relations": [
                {
                    "type": "RELATED_TO",
                    "from": "industry_cloud_service",
                    "to": "industry_it",
                    "evidence": "Cloud service is related to IT.",
                },
                {
                    "type": "PART_OF",
                    "from": "industry_cloud_service",
                    "to": "industry_it",
                    "evidence": "Cloud service is part of IT.",
                },
                {
                    "type": "PART_OF",
                    "from": "industry_it",
                    "to": "industry_it",
                    "evidence": "IT is part of IT.",
                },
            ],
        }

        normalized = normalize_graph_roles(graph)

        self.assertIn(
            {
                "type": "PART_OF",
                "from": "industry_cloud_service",
                "to": "industry_it_software",
                "evidence": "Cloud service is part of IT.",
            },
            normalized["relations"],
        )
        self.assertFalse(
            any(
                relation["type"] == "RELATED_TO"
                and {relation["from"], relation["to"]} == {"industry_cloud_service", "industry_it_software"}
                for relation in normalized["relations"]
            )
        )

    def test_graph_normalization_adds_dart_executive_relation_role_fields(self):
        whitelist = CompanyWhitelist([ListedCompany("000270", "Kia", "KOSPI")])
        graph = {
            "source_id": "dart_000270_executive_status_2025_11011",
            "entities": [
                {
                    "id": "person_chung",
                    "type": "Person",
                    "name": "Chung Euisun",
                    "role": "CEO",
                    "role_raw": "CEO",
                },
            ],
            "relations": [],
        }
        source_doc = {
            "source_id": "dart_000270_executive_status_2025_11011",
            "document_type": "dart",
            "dataset": "executive_status",
            "company_name": "Kia",
            "stock_code": "000270",
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312001224",
            "published_at": "2026-03-12",
            "normalized_records": [
                {
                    "nm": "Chung Euisun",
                    "birth_ym": "1970.10",
                    "ofcps": "chairman",
                    "rgist_exctv_at": "inside director",
                    "fte_at": "full-time",
                    "chrg_job": "Hyundai Motor Group chairman",
                    "main_career": "Hyundai Motor Group chairman",
                    "mxmm_shrholdr_relate": "executive",
                    "hffc_pd": "1 year",
                    "tenure_end_on": "2028.03.14",
                }
            ],
        }

        normalized = normalize_graph_roles(graph, whitelist, source_doc)
        person = next(entity for entity in normalized["entities"] if entity["type"] == "Person")
        relation = normalized["relations"][0]

        self.assertEqual(person["id"], "person_chung_euisun_197010")
        self.assertEqual(person["birth_ym"], "1970-10")
        self.assertEqual(person["main_career"], "Hyundai Motor Group chairman")
        self.assertNotIn("role", person)
        self.assertNotIn("role_raw", person)
        self.assertEqual(relation["type"], "AFFILIATED_WITH")
        self.assertEqual(relation["from"], "person_chung_euisun_197010")
        self.assertEqual(relation["to"], "company_000270")
        self.assertEqual(relation["role"], "CHAIRMAN")
        self.assertEqual(relation["role_raw"], "chairman")
        self.assertEqual(relation["role_label"], "회장")
        self.assertEqual(relation["board_role"], "inside director")
        self.assertEqual(relation["responsibility"], "Hyundai Motor Group chairman")
        validate(instance=normalized, schema=__import__("json").loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8")))

    def legacy_graph_normalization_adds_dart_executive_person_identity(self):
        whitelist = CompanyWhitelist([ListedCompany("267250", "HD현대", "KOSPI")])
        graph = {
            "source_id": "dart_267250_executive_status_2025_11011",
            "entities": [
                {"id": "person_권오갑", "type": "Person", "name": "권오갑"},
            ],
            "relations": [],
        }
        source_doc = {
            "source_id": "dart_267250_executive_status_2025_11011",
            "document_type": "dart",
            "dataset": "executive_status",
            "company_name": "HD현대",
            "stock_code": "267250",
            "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260320000872",
            "published_at": "2026-03-20",
            "normalized_records": [
                {
                    "nm": "권오갑",
                    "sexdstn": "남",
                    "birth_ym": "1951년 02월",
                    "ofcps": "대표이사",
                    "rgist_exctv_at": "사내이사",
                    "fte_at": "상근",
                    "chrg_job": "대표이사",
                    "main_career": "2025~현재 : HD현대 명예회장",
                    "mxmm_shrholdr_relate": "계열회사 임원",
                    "hffc_pd": "8년",
                    "tenure_end_on": "2026년 03월 28일",
                }
            ],
        }

        normalized = normalize_graph_roles(graph, whitelist, source_doc)
        person = next(entity for entity in normalized["entities"] if entity["type"] == "Person")

        self.assertEqual(person["id"], "person_권오갑_195102")
        self.assertEqual(person["birth_ym"], "1951-02")
        self.assertEqual(person["gender"], "남")
        self.assertEqual(person["main_career"], "2025~현재 : HD현대 명예회장")
        self.assertEqual(person["executive_type"], "사내이사")
        self.assertEqual(
            normalized["relations"][0]["type"],
            "AFFILIATED_WITH",
        )
        self.assertEqual(normalized["relations"][0]["from"], "person_권오갑_195102")
        self.assertEqual(normalized["relations"][0]["to"], "company_267250")
        validate(instance=normalized, schema=__import__("json").loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8")))

    def test_graph_normalization_removes_person_entities_from_news(self):
        whitelist = CompanyWhitelist([ListedCompany("005930", "Samsung Electronics", "KOSPI")])
        graph = {
            "source_id": "news_001",
            "entities": [
                {
                    "id": "company_samsung_electronics",
                    "type": "Company",
                    "name": "Samsung Electronics",
                },
                {"id": "person_jane_doe", "type": "Person", "name": "Jane Doe"},
            ],
            "relations": [
                {
                    "type": "AFFILIATED_WITH",
                    "from": "person_jane_doe",
                    "to": "company_samsung_electronics",
                    "evidence": "Jane Doe is affiliated with Samsung Electronics.",
                }
            ],
        }
        source_doc = {
            "source_id": "news_001",
            "document_type": "news",
            "url": "https://example.com/news/1",
            "published_at": "2026-05-12T10:00:00+09:00",
        }

        normalized = normalize_graph_roles(graph, whitelist, source_doc)

        self.assertFalse(any(entity["type"] == "Person" for entity in normalized["entities"]))
        self.assertEqual(normalized["relations"], [])


if __name__ == "__main__":
    unittest.main()

