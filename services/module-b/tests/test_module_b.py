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


if __name__ == "__main__":
    unittest.main()
