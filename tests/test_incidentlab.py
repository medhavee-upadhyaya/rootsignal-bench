from __future__ import annotations

import unittest
from pathlib import Path

from incidentlab.agent import Investigator
from incidentlab.evaluation import score
from incidentlab.fixtures import load_incident
from incidentlab.retrieval import bm25_search


FIXTURE = Path("fixtures/incidents/checkout_latency.yaml")


class IncidentLabTests(unittest.TestCase):
    def test_fixture_loads(self) -> None:
        incident = load_incident(FIXTURE)
        self.assertEqual(incident.incident_id, "checkout-latency-001")

    def test_retrieval_ranks_pool_runbook_first(self) -> None:
        incident = load_incident(FIXTURE)
        results = bm25_search("database pool wait connections", incident.runbooks)
        self.assertEqual(results[0]["id"], "db-pool-exhaustion")

    def test_end_to_end_baseline(self) -> None:
        incident = load_incident(FIXTURE)
        result = Investigator().investigate(incident)
        scorecard = score(incident, result)
        self.assertEqual(len(result.tool_calls), 4)
        self.assertGreaterEqual(scorecard.overall, 0.80)

    def test_tool_budget_is_enforced(self) -> None:
        incident = load_incident(FIXTURE)
        result = Investigator(max_tool_calls=2).investigate(incident)
        self.assertEqual(len(result.tool_calls), 2)


if __name__ == "__main__":
    unittest.main()
