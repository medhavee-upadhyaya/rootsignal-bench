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

    def test_reviews_are_append_only_and_do_not_mutate_run_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            run = store.save(
                incident_id="checkout-latency-001", incident_title="Checkout latency",
                mode="model", model="test-model", query="Investigate checkout",
                fixture_sha256="d" * 64, result={"root_cause": "Pool exhaustion"}, metadata={},
            )
            first = store.add_review(run["run_id"], "needs_investigation", "Check deployment timing")
            second = store.add_review(run["run_id"], "accepted", "Confirmed by database team")
            record = store.get(run["run_id"])
            assert record is not None
            self.assertEqual([item["review_id"] for item in record["reviews"]], [first["review_id"], second["review_id"]])
            self.assertEqual(record["result"]["root_cause"], "Pool exhaustion")
            with self.assertRaisesRegex(ValueError, "Unknown run"):
                store.add_review("0" * 32, "rejected")

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

    def test_run_filters_compose_with_cursor_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            matching = []
            for index in range(4):
                run = store.save(
                    incident_id="checkout" if index < 3 else "billing",
                    incident_title="Incident", mode="model" if index != 1 else "baseline",
                    model="test", query="Investigate", fixture_sha256="e" * 64,
                    result={}, metadata={},
                )
                if index in {0, 2}:
                    store.add_review(run["run_id"], "accepted")
                    matching.append(run["run_id"])
            first = store.list(limit=1, incident_id="checkout", mode="model", review="accepted")
            second = store.list(
                limit=1, cursor=first[0]["run_id"], incident_id="checkout",
                mode="model", review="accepted",
            )
            observed = [first[0]["run_id"], second[0]["run_id"]]
            self.assertEqual(set(observed), set(matching))

    def test_latest_model_runs_selects_one_per_incident_from_complete_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            older = store.save(
                incident_id="checkout", incident_title="Checkout", mode="model",
                model="old-model", query="Investigate", fixture_sha256="a" * 64,
                result={"root_cause": "old"}, metadata={},
            )
            store.save(
                incident_id="checkout", incident_title="Checkout", mode="baseline",
                model="control", query="Investigate", fixture_sha256="a" * 64,
                result={}, metadata={},
            )
            newer = store.save(
                incident_id="checkout", incident_title="Checkout", mode="model",
                model="new-model", query="Investigate", fixture_sha256="a" * 64,
                result={"root_cause": "new"}, metadata={},
            )
            billing = store.save(
                incident_id="billing", incident_title="Billing", mode="model",
                model="new-model", query="Investigate", fixture_sha256="b" * 64,
                result={"root_cause": "billing"}, metadata={},
            )

            selected = store.latest_model_runs_by_incident()
            selected_ids = {run["run_id"] for run in selected}
            self.assertEqual(selected_ids, {newer["run_id"], billing["run_id"]})
            self.assertNotIn(older["run_id"], selected_ids)
            self.assertTrue(all(run["mode"] == "model" for run in selected))


if __name__ == "__main__":
    unittest.main()
