from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from incidentlab.fixtures import load_incident
from incidentlab.knowledge import KnowledgeBase
from incidentlab.llm import Generation
from incidentlab.rag_agent import GroundedAgent


class FakeLLM:
    model = "fake-model"

    def __init__(self) -> None:
        self.plans = iter(["query_metrics", "query_logs", "query_deployments", "retrieve_knowledge"])

    def generate_json(self, system: str, user: str, max_tokens: int = 500) -> Generation:
        if "single best next" in system:
            content = json.dumps({"name": next(self.plans), "arguments": {}})
        else:
            content = json.dumps(
                {
                    "root_cause": "DB_POOL_SIZE was reduced from 40 to 10 and exhausted the pool.",
                    "confidence": 0.9,
                    "citations": [1, 3],
                    "remediation": ["Restore the safe pool size"],
                }
            )
        return Generation(content, self.model, 1.0, 10, 5)


class GroundedAgentTests(unittest.TestCase):
    def test_model_plans_bounded_tools_and_retrieves_knowledge(self) -> None:
        incident = load_incident("fixtures/incidents/checkout_latency.yaml")
        with tempfile.TemporaryDirectory() as directory:
            knowledge = KnowledgeBase(Path(directory) / "knowledge.db")
            knowledge.ingest("runbook/db-pool", incident.runbooks[0]["content"])
            result = GroundedAgent(knowledge, FakeLLM()).investigate(incident.summary, incident)  # type: ignore[arg-type]
        self.assertEqual(result["run"]["agent_steps"], 4)  # type: ignore[index]
        self.assertEqual(result["run"]["model_planned_steps"], 4)  # type: ignore[index]
        self.assertEqual(result["run"]["retrieved_chunks"], 1)  # type: ignore[index]
        self.assertEqual([call["name"] for call in result["tool_calls"]], list(GroundedAgent.TOOL_DESCRIPTIONS))  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
