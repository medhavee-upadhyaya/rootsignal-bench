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

    def __init__(self, citations: list[int] | None = None) -> None:
        self.plans = iter(["query_metrics", "query_logs", "query_deployments", "retrieve_knowledge"])
        self.citations = citations if citations is not None else [1, 3]

    def generate_json(self, system: str, user: str, max_tokens: int = 500) -> Generation:
        if "single best next" in system:
            content = json.dumps({"name": next(self.plans), "arguments": {}})
        else:
            content = json.dumps(
                {
                    "root_cause": "DB_POOL_SIZE was reduced from 40 to 10 and exhausted the pool.",
                    "confidence": 0.9,
                    "citations": self.citations,
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
        self.assertEqual(result["run"]["grounding"]["status"], "limited")  # type: ignore[index]
        self.assertEqual(result["confidence"], 0.65)
        self.assertEqual([call["name"] for call in result["tool_calls"]], list(GroundedAgent.TOOL_DESCRIPTIONS))  # type: ignore[index]

    def test_withholds_diagnosis_when_model_returns_no_valid_citations(self) -> None:
        incident = load_incident("fixtures/incidents/checkout_latency.yaml")
        with tempfile.TemporaryDirectory() as directory:
            knowledge = KnowledgeBase(Path(directory) / "knowledge.db")
            result = GroundedAgent(knowledge, FakeLLM([])).investigate(incident.summary, incident)  # type: ignore[arg-type]
        self.assertEqual(result["run"]["grounding"]["status"], "insufficient")  # type: ignore[index]
        self.assertEqual(result["confidence"], 0.25)
        self.assertEqual(result["root_cause"], "Insufficient cited evidence to support a diagnosis.")
        self.assertIn("diagnosis was withheld", result["limitations"][-1])

    def test_preserves_confidence_when_citations_span_signal_sources(self) -> None:
        incident = load_incident("fixtures/incidents/checkout_latency.yaml")
        with tempfile.TemporaryDirectory() as directory:
            knowledge = KnowledgeBase(Path(directory) / "knowledge.db")
            result = GroundedAgent(knowledge, FakeLLM([1, 5])).investigate(incident.summary, incident)  # type: ignore[arg-type]
        self.assertEqual(result["run"]["grounding"]["status"], "grounded")  # type: ignore[index]
        self.assertEqual(result["confidence"], 0.9)


if __name__ == "__main__":
    unittest.main()
