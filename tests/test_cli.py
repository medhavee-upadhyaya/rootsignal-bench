from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from incidentlab.cli import MAX_KNOWLEDGE_FILE_BYTES, main
from incidentlab.knowledge import KnowledgeBase


class RootSignalCliTests(unittest.TestCase):
    def test_ingest_indexes_a_file_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "knowledge.db"
            runbook = root / "pool.md"
            runbook.write_text(
                "Database pool saturation increases checkout wait time.", encoding="utf-8"
            )

            payloads = []
            for _ in range(2):
                output = io.StringIO()
                with redirect_stdout(output):
                    main([
                        "ingest", str(runbook), "--source", "runbook/db-pool",
                        "--db", str(database),
                    ])
                payloads.append(json.loads(output.getvalue()))

            self.assertEqual(payloads[0]["status"], "indexed")
            self.assertGreater(payloads[0]["chunks"], 0)
            self.assertEqual(payloads[1]["status"], "unchanged")
            results = KnowledgeBase(database).search("checkout pool wait")
            self.assertEqual(results[0].source, "runbook/db-pool")

    def test_ingest_rejects_oversized_files_before_opening_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runbook = root / "oversized.md"
            runbook.write_bytes(b"x" * (MAX_KNOWLEDGE_FILE_BYTES + 1))
            error = io.StringIO()

            with redirect_stderr(error), self.assertRaises(SystemExit):
                main([
                    "ingest", str(runbook), "--source", "runbook/large",
                    "--db", str(root / "knowledge.db"),
                ])

            self.assertIn("exceeds the 1 MB limit", error.getvalue())
            self.assertFalse((root / "knowledge.db").exists())

    def test_search_exposes_ranked_provenance_and_scores(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "knowledge.db"
            knowledge = KnowledgeBase(database)
            knowledge.ingest(
                "runbook/db-pool",
                "Database connection pool saturation causes checkout wait time.",
            )
            knowledge.ingest(
                "runbook/certificates", "Rotate TLS certificates before expiration."
            )
            output = io.StringIO()

            with redirect_stdout(output):
                main([
                    "search", "checkout database pool wait",
                    "--db", str(database), "--limit", "1",
                ])

            payload = json.loads(output.getvalue())
            self.assertEqual(payload["strategy"], "reranked")
            self.assertEqual(payload["count"], 1)
            result = payload["results"][0]
            self.assertEqual(result["rank"], 1)
            self.assertEqual(result["source"], "runbook/db-pool")
            for field in ("chunk_id", "lexical_score", "semantic_score", "rerank_score"):
                self.assertIn(field, result)

    def test_search_respects_collection_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "knowledge.db"
            knowledge = KnowledgeBase(database)
            knowledge.create_collection("team-private", "Team private")
            knowledge.ingest(
                "private/runbook",
                "Checkout database pool saturation response.",
                "team-private",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                main([
                    "search", "checkout database pool", "--db", str(database),
                    "--collection", "incident-runbooks",
                ])

            payload = json.loads(output.getvalue())
            self.assertEqual(payload["count"], 0)
            self.assertEqual(payload["collections"], ["incident-runbooks"])


if __name__ == "__main__":
    unittest.main()
