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
    def test_collections_create_and_list_scoped_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "knowledge.db"
            created_output = io.StringIO()
            with redirect_stdout(created_output):
                main([
                    "collections", "create", "payments-team",
                    "--name", "Payments team",
                    "--description", "Private payment service runbooks",
                    "--db", str(database),
                ])

            created = json.loads(created_output.getvalue())
            self.assertEqual(created["id"], "payments-team")
            self.assertEqual(created["name"], "Payments team")

            listed_output = io.StringIO()
            with redirect_stdout(listed_output):
                main(["collections", "list", "--db", str(database)])

            listed = json.loads(listed_output.getvalue())
            by_id = {item["id"]: item for item in listed["collections"]}
            self.assertEqual(listed["count"], 2)
            self.assertIn("incident-runbooks", by_id)
            self.assertEqual(by_id["payments-team"]["documents"], 0)

    def test_collections_reject_invalid_or_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "knowledge.db"
            error = io.StringIO()
            command = [
                "collections", "create", "invalid id", "--name", "Invalid",
                "--db", str(database),
            ]
            with redirect_stderr(error), self.assertRaises(SystemExit):
                main(command)
            self.assertIn("lowercase letters, digits, and hyphens", error.getvalue())

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
