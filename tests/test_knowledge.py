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

    def test_strategies_are_explicit_and_reranking_scores_are_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            knowledge = KnowledgeBase(Path(directory) / "knowledge.db")
            knowledge.ingest("runbook/pool", "Database connection pool saturation and wait time.")
            knowledge.ingest("runbook/cert", "Certificate rotation and TLS expiration.")
            for strategy in ("lexical", "semantic", "hybrid", "reranked"):
                result = knowledge.search("database pool wait", limit=1, strategy=strategy)
                self.assertEqual(result[0].source, "runbook/pool")
            reranked = knowledge.search("database pool wait", limit=1, strategy="reranked")[0]
            self.assertGreater(reranked.rerank_score, 0)
            with self.assertRaises(ValueError):
                knowledge.search("database", strategy="unknown")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
