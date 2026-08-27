from __future__ import annotations

import unittest

from incidentlab.comparison import compare_runs
from incidentlab.fixtures import load_incident


def stored_run(run_id: str, incident_id: str, *, root_cause: str, latency_ms: float) -> dict:
    return {
        "run_id": run_id,
        "created_at": "2026-08-26T00:00:00.000Z",
        "incident_id": incident_id,
        "mode": "model",
        "model": "test-model",
        "fixture_sha256": "a" * 64,
        "metadata": {"latency_ms": latency_ms},
        "result": {
            "incident_id": incident_id,
            "root_cause": root_cause,
            "confidence": 0.8,
            "evidence": [],
            "remediation": [],
            "tool_calls": [],
        },
    }


class ComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.incident = load_incident("fixtures/incidents/checkout_latency.yaml")

    def test_detects_material_quality_improvement(self) -> None:
        reference = stored_run(
            "reference", self.incident.incident_id, root_cause="unknown", latency_ms=1000
        )
        candidate = stored_run(
            "candidate",
            self.incident.incident_id,
            root_cause=self.incident.oracle["root_cause"],
            latency_ms=1050,
        )
        comparison = compare_runs(self.incident, reference, candidate)
        self.assertEqual(comparison["verdict"], "improved")
        self.assertGreater(comparison["deltas"]["overall"], 0)

    def test_detects_latency_regression_without_quality_gain(self) -> None:
        cause = self.incident.oracle["root_cause"]
        reference = stored_run(
            "reference", self.incident.incident_id, root_cause=cause, latency_ms=1000
        )
        candidate = stored_run(
            "candidate", self.incident.incident_id, root_cause=cause, latency_ms=1500
        )
        comparison = compare_runs(self.incident, reference, candidate)
        self.assertEqual(comparison["verdict"], "regressed")
        self.assertEqual(comparison["deltas"]["latency_percent"], 50)

    def test_rejects_different_incidents_and_fixture_revisions(self) -> None:
        reference = stored_run(
            "reference", self.incident.incident_id, root_cause="unknown", latency_ms=1
        )
        candidate = stored_run("candidate", "different", root_cause="unknown", latency_ms=1)
        with self.assertRaisesRegex(ValueError, "same incident"):
            compare_runs(self.incident, reference, candidate)
        candidate["incident_id"] = self.incident.incident_id
        candidate["fixture_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "fixture revision"):
            compare_runs(self.incident, reference, candidate)


if __name__ == "__main__":
    unittest.main()
