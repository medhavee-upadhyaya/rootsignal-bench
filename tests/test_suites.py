from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from incidentlab.agent import Investigator
from incidentlab.fixtures import load_incident
from incidentlab.suites import build_suite, main, verify_suite


def stored_model_run(incident, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "mode": "model",
        "model": "test-model",
        "result": Investigator().investigate(incident).as_dict(),
    }


class EvaluationSuiteTests(unittest.TestCase):
    def test_aggregates_distinct_incidents_with_deterministic_intervals(self) -> None:
        first = load_incident("fixtures/incidents/checkout_latency.yaml")
        second = load_incident("fixtures/incidents/billing_clock.json")
        report = build_suite([
            (second, stored_model_run(second, "b" * 32)),
            (first, stored_model_run(first, "a" * 32)),
        ])
        self.assertEqual(report["fixture_count"], 2)
        self.assertEqual([row["incident_id"] for row in report["incidents"]], sorted([first.incident_id, second.incident_id]))
        self.assertEqual(report["confidence_intervals"]["overall"]["bootstrap_samples"], 2_000)
        self.assertTrue(verify_suite(report))
        tampered = json.loads(json.dumps(report))
        tampered["aggregate"]["overall"] = 1.0
        self.assertFalse(verify_suite(tampered))

    def test_selection_manifest_is_covered_by_integrity_digest(self) -> None:
        first = load_incident("fixtures/incidents/checkout_latency.yaml")
        second = load_incident("fixtures/incidents/billing_clock.json")
        report = build_suite(
            [
                (first, stored_model_run(first, "a" * 32)),
                (second, stored_model_run(second, "b" * 32)),
            ],
            selection={
                "strategy": "latest_model_run_per_incident",
                "candidate_count": 2,
                "included_run_ids": ["a" * 32, "b" * 32],
                "excluded": [],
            },
        )
        self.assertTrue(verify_suite(report))
        report["selection"]["included_run_ids"].pop()
        self.assertFalse(verify_suite(report))

    def test_rejects_oracle_controls_and_duplicate_incidents(self) -> None:
        incident = load_incident("fixtures/incidents/checkout_latency.yaml")
        first = stored_model_run(incident, "a" * 32)
        second = stored_model_run(incident, "b" * 32)
        with self.assertRaisesRegex(ValueError, "one run per incident"):
            build_suite([(incident, first), (incident, second)])
        second["mode"] = "baseline"
        other = load_incident("fixtures/incidents/billing_clock.json")
        with self.assertRaisesRegex(ValueError, "model-backed runs only"):
            build_suite([(incident, first), (other, second)])

    def test_offline_verifier_accepts_valid_file_and_rejects_tampering(self) -> None:
        first = load_incident("fixtures/incidents/checkout_latency.yaml")
        second = load_incident("fixtures/incidents/billing_clock.json")
        report = build_suite([
            (first, stored_model_run(first, "a" * 32)),
            (second, stored_model_run(second, "b" * 32)),
        ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([str(path)]), 0)
            self.assertIn(report["integrity"]["digest"], output.getvalue())

            report["aggregate"]["overall"] = 1.0
            path.write_text(json.dumps(report), encoding="utf-8")
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertEqual(main([str(path)]), 1)
            self.assertIn("integrity verification failed", error.getvalue())


if __name__ == "__main__":
    unittest.main()
