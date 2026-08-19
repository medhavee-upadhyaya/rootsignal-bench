from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from incidentlab.knowledge import KnowledgeBase, chunk_text


class KnowledgeBaseTests(unittest.TestCase):
    def test_chunking_preserves_overlap_and_content(self) -> None:
        chunks = chunk_text("database pool exhaustion " * 80, size=120, overlap=20)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))

    def test_ingest_is_idempotent_and_search_returns_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            knowledge = KnowledgeBase(Path(directory) / "knowledge.db")
            first = knowledge.ingest("runbook/pool", "Database pool wait time indicates saturation." * 2)
            second = knowledge.ingest("runbook/pool", "Database pool wait time indicates saturation." * 2)
            results = knowledge.search("database pool saturation")
            self.assertEqual(first["status"], "indexed")
            self.assertEqual(second["status"], "unchanged")
            self.assertEqual(results[0].source, "runbook/pool")
            self.assertGreater(results[0].semantic_score, 0)
            self.assertGreater(results[0].score, 0)

    def test_hybrid_search_recovers_semantic_bigram_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            knowledge = KnowledgeBase(Path(directory) / "knowledge.db")
            knowledge.ingest("runbook/cache", "Repeated cache eviction causes elevated origin traffic.")
            knowledge.ingest("runbook/certs", "TLS certificates must rotate before expiration.")
            results = knowledge.search("cache eviction origin traffic", limit=1)
            self.assertEqual(results[0].source, "runbook/cache")


if __name__ == "__main__":
    unittest.main()
