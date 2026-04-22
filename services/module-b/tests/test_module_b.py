from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chunking import split_text_into_chunks
from document_io import iter_input_documents
from graph_pipeline import extract_graph as extract_graph_from_pipeline
from mock_extract_graph import extract_graph


TEST_DIR = Path(__file__).resolve().parent


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ModuleBPipelineTests(unittest.TestCase):
    def test_chunking_produces_multiple_chunks(self):
        doc = load_json(TEST_DIR / "sample_news_01.json")
        chunks = split_text_into_chunks(doc, max_chunk_length=80)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["doc_id"], "news_001")
        self.assertIn("카카오", chunks[0]["company_hint"])

    def test_extract_graph_acquisition(self):
        doc = load_json(TEST_DIR / "sample_news_01.json")
        graph = extract_graph(doc)

        relation_types = {relation["type"] for relation in graph["relations"]}
        self.assertIn("ACQUIRES", relation_types)
        self.assertIn("BELONGS_TO", relation_types)

    def test_extract_graph_investment(self):
        doc = load_json(TEST_DIR / "sample_news_02.json")
        graph = extract_graph(doc)

        relation_types = {relation["type"] for relation in graph["relations"]}
        self.assertIn("INVESTS_IN", relation_types)
        self.assertIn("BELONGS_TO", relation_types)

    def test_extract_graph_appointment(self):
        doc = load_json(TEST_DIR / "sample_news_03.json")
        graph = extract_graph(doc)

        relation_types = {relation["type"] for relation in graph["relations"]}
        self.assertIn("APPOINTED_TO", relation_types)
        self.assertIn("AFFILIATED_WITH", relation_types)

    def test_jsonl_input_loading(self):
        docs = iter_input_documents(TEST_DIR / "sample_news_batch.jsonl")
        self.assertEqual(len(docs), 3)
        self.assertEqual(docs[0]["source_id"], "news_001")

    def test_graph_pipeline_rule_mode(self):
        doc = load_json(TEST_DIR / "sample_news_02.json")
        graph = extract_graph_from_pipeline(doc, mode="rule")
        relation_types = {relation["type"] for relation in graph["relations"]}
        self.assertIn("INVESTS_IN", relation_types)


if __name__ == "__main__":
    unittest.main()
