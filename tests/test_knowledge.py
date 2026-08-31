from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from incidentlab.knowledge import KnowledgeBase, chunk_text


class KnowledgeBaseTests(unittest.TestCase):
    def test_collections_isolate_retrieval_and_survive_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.db"
            knowledge = KnowledgeBase(path)
            knowledge.create_collection("payments", "Payments")
            knowledge.create_collection("search", "Search")
            knowledge.ingest(
                "runbook/payments", "Neon badger payment retries require idempotency keys.", "payments"
            )
            knowledge.ingest(
                "runbook/search", "Neon badger search errors require shard recovery.", "search"
            )

            payments = knowledge.search("neon badger", collection_ids=["payments"])
            search = KnowledgeBase(path).search("neon badger", collection_ids=["search"])

            self.assertEqual(payments[0].source, "runbook/payments")
            self.assertEqual(search[0].source, "runbook/search")
            self.assertEqual(
                {item["id"] for item in KnowledgeBase(path).list_collections()},
                {"incident-runbooks", "payments", "search"},
            )

    def test_legacy_documents_are_quarantined_from_system_runbooks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "knowledge.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE documents (
                        id TEXT PRIMARY KEY, source TEXT NOT NULL, content TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
                    );
                    CREATE VIRTUAL TABLE chunks USING fts5(
                        chunk_id UNINDEXED, document_id UNINDEXED, source, content
                    );
                    INSERT INTO documents VALUES (
                        'legacy-doc', 'private/note', 'secret zebra procedure',
                        'legacy-hash', CURRENT_TIMESTAMP
                    );
                    INSERT INTO chunks VALUES (
                        'legacy-doc:0', 'legacy-doc', 'private/note', 'secret zebra procedure'
                    );
                    """
                )
            finally:
                connection.close()

            knowledge = KnowledgeBase(path)
            self.assertEqual(knowledge.search("secret zebra"), [])
            self.assertEqual(
                knowledge.search("secret zebra", collection_ids=["legacy-imports"])[0].source,
                "private/note",
            )

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

    def test_reranking_preserves_specific_lexical_evidence_in_long_queries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            knowledge = KnowledgeBase(Path(directory) / "knowledge.db")
            knowledge.ingest(
                "runbook/db-pool",
                "Pool wait rises when active connections reach capacity. Restore the safe pool size.",
            )
            for index in range(30):
                knowledge.ingest(
                    f"runbook/distractor-{index}",
                    f"Generic deployment latency operations note number {index}.",
                )
            noise = " ".join(f"noise{index}" for index in range(90))
            query = f"deployment latency {noise} db pool wait active connections capacity"
            results = knowledge.search(query, limit=2, strategy="reranked")
            self.assertEqual(results[0].source, "runbook/db-pool")


if __name__ == "__main__":
    unittest.main()
