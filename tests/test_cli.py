from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from incidentlab.cli import main
from incidentlab.knowledge import KnowledgeBase


class RootSignalCliTests(unittest.TestCase):
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
