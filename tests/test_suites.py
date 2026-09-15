from __future__ import annotations

import unittest

from incidentlab.agent import Investigator
from incidentlab.fixtures import load_incident
from incidentlab.suites import build_suite


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


if __name__ == "__main__":
    unittest.main()
