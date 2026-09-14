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

    def test_cursor_pagination_is_stable_and_has_no_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            saved = []
            for index in range(5):
                saved.append(store.save(
                    incident_id=f"incident-{index}", incident_title=f"Incident {index}",
                    mode="baseline", model="deterministic-v1", query="Investigate",
                    fixture_sha256="c" * 64, result={}, metadata={},
                )["run_id"])
            first = store.list(limit=2)
            second = store.list(limit=2, cursor=first[-1]["run_id"])
            third = store.list(limit=2, cursor=second[-1]["run_id"])
            observed = [item["run_id"] for item in [*first, *second, *third]]
            self.assertEqual(len(observed), 5)
            self.assertEqual(len(set(observed)), 5)
            self.assertEqual(set(observed), set(saved))
            with self.assertRaisesRegex(ValueError, "Unknown run cursor"):
                store.list(cursor="missing")


if __name__ == "__main__":
    unittest.main()
