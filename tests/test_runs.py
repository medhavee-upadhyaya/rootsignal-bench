from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from incidentlab.runs import RunStore


class RunStoreTests(unittest.TestCase):
    def test_run_survives_store_reopen_and_preserves_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.db"
            store = RunStore(path)
            reference = store.save(
                incident_id="checkout-latency-001",
                incident_title="Checkout latency after deployment",
                mode="model",
                model="qwen3:1.7b",
                query="Investigate checkout latency",
                fixture_sha256="a" * 64,
                result={"confidence": 0.82, "tool_calls": [{"name": "query_metrics"}], "evidence": []},
                metadata={"latency_ms": 1250.5, "api_version": "0.2.0"},
            )

            reopened = RunStore(path)
            record = reopened.get(reference["run_id"])
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record["mode"], "model")
            self.assertEqual(record["result"]["confidence"], 0.82)
            self.assertEqual(record["metadata"]["latency_ms"], 1250.5)
            self.assertEqual(reopened.list()[0]["run_id"], reference["run_id"])

    def test_list_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            for index in range(3):
                store.save(
                    incident_id=f"incident-{index}",
                    incident_title=f"Incident {index}",
                    mode="baseline",
                    model="deterministic-v1",
                    query="Investigate",
                    fixture_sha256="b" * 64,
                    result={},
                    metadata={},
                )
            self.assertEqual(len(store.list(limit=2)), 2)
            self.assertEqual(len(store.list(limit=1000)), 3)


if __name__ == "__main__":
    unittest.main()
