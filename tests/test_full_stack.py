from __future__ import annotations

import io
import json
import unittest
import urllib.error
import uuid
from unittest.mock import patch

try:
    from incidentlab.api import METRICS
    from incidentlab.evidence_bundle import verify_evidence_bundle
    from tests.test_api import asgi_request
except (ImportError, RuntimeError):
    METRICS = None  # type: ignore[assignment]


class MockResponse(io.BytesIO):
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        super().__init__(json.dumps(payload).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class OpenAIProvider:
    def __init__(self) -> None:
        self.plans = iter(
            ["query_metrics", "query_logs", "query_deployments", "retrieve_knowledge"]
        )
        self.requests: list[dict[str, object]] = []

    def urlopen(self, request: object, timeout: float = 0) -> MockResponse:
        self.assert_request(request, timeout)
        body = json.loads(request.data)  # type: ignore[attr-defined]
        self.requests.append(body)
        system = body["messages"][0]["content"]
        if "single best next" in system:
            content = json.dumps({"name": next(self.plans), "arguments": {}})
        else:
            content = json.dumps(
                {
                    "root_cause": "v1.8.3 reduced DB_POOL_SIZE and exhausted connections",
                    "confidence": 0.93,
                    "citations": [1, 10],
                    "remediation": ["Restore DB_POOL_SIZE to 40"],
                }
            )
        return MockResponse(
            {
                "model": "mock-openai-compatible-model",
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            }
        )

    @staticmethod
    def assert_request(request: object, timeout: float) -> None:
        if not hasattr(request, "data"):
            raise AssertionError("expected a POST request object")
        if timeout != 120:
            raise AssertionError("model request timeout contract changed")


@unittest.skipIf(METRICS is None, "API dependencies are not installed")
class FullStackInvestigationTests(unittest.TestCase):
    def test_saved_model_runs_produce_a_multi_incident_suite(self) -> None:
        run_ids = []
        for incident_id in ("checkout-latency-001", "billing-clock-001"):
            provider = OpenAIProvider()
            with patch("incidentlab.llm.urllib.request.urlopen", side_effect=provider.urlopen):
                status, _, result = asgi_request(
                    "POST", "/v1/investigations", body={"incident_id": incident_id}
                )
            self.assertEqual(status, 200)
            run_ids.append(result["record"]["run_id"])

        status, _, report = asgi_request(
            "POST", "/v1/evaluation-suites", body={"run_ids": run_ids}
        )

        self.assertEqual(status, 200)
        self.assertEqual(report["kind"], "saved-model-run-suite")
        self.assertEqual(report["fixture_count"], 2)
        self.assertEqual(len(report["incidents"]), 2)
        self.assertIn("overall", report["aggregate"])
        self.assertEqual(report["confidence_intervals"]["overall"]["confidence"], 0.95)
        self.assertNotIn('"oracle"', json.dumps(report).lower())

    def test_new_user_journey_creates_verifiable_comparison_evidence(self) -> None:
        collection_id = f"journey-{uuid.uuid4().hex}"
        status, _, collection = asgi_request(
            "POST",
            "/v1/knowledge/collections",
            body={"id": collection_id, "name": "Checkout operations"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(collection["id"], collection_id)

        status, _, indexed = asgi_request(
            "POST",
            "/v1/knowledge",
            body={
                "collection_id": collection_id,
                "source": "runbook/checkout-pool",
                "text": (
                    "If checkout latency follows a deployment, compare DB_POOL_SIZE with the "
                    "previous release and restore the last safe value before scaling replicas. "
                    f"Acceptance journey {collection_id}."
                ),
            },
        )
        self.assertEqual(status, 200)
        self.assertGreater(indexed["chunks"], 0)

        request = {
            "incident_id": "checkout-latency-001",
            "collection_ids": ["incident-runbooks", collection_id],
        }
        status, _, control = asgi_request(
            "POST", "/v1/baselines/deterministic", body=request
        )
        self.assertEqual(status, 200)
        self.assertEqual(control["record"]["mode"], "baseline")

        provider = OpenAIProvider()
        with patch("incidentlab.llm.urllib.request.urlopen", side_effect=provider.urlopen):
            status, _, agent = asgi_request("POST", "/v1/investigations", body=request)
        self.assertEqual(status, 200)
        self.assertEqual(agent["record"]["mode"], "model")

        control_id = control["record"]["run_id"]
        agent_id = agent["record"]["run_id"]
        _, _, stored_agent = asgi_request("GET", f"/v1/runs/{agent_id}")
        self.assertEqual(
            stored_agent["metadata"]["knowledge_collections"],
            ["incident-runbooks", collection_id],
        )
        status, _, comparison = asgi_request(
            "POST",
            "/v1/comparisons",
            body={"reference_run_id": control_id, "candidate_run_id": agent_id},
        )
        self.assertEqual(status, 200)
        self.assertEqual(comparison["reference"]["run"]["run_id"], control_id)
        self.assertEqual(comparison["candidate"]["run"]["run_id"], agent_id)
        self.assertIn(comparison["verdict"], {"improved", "regressed", "unchanged"})

        status, headers, bundle = asgi_request(
            "GET", f"/v1/runs/{control_id}/export?compare_to={agent_id}"
        )
        self.assertEqual(status, 200)
        self.assertIn(control_id, headers["content-disposition"])
        self.assertTrue(verify_evidence_bundle(bundle))
        self.assertEqual(bundle["comparison"]["candidate"]["run"]["run_id"], agent_id)
        self.assertNotIn('"oracle"', json.dumps(bundle).lower())

    def test_public_api_runs_model_tools_rag_citations_and_metrics(self) -> None:
        provider = OpenAIProvider()
        before = METRICS.snapshot()
        with patch("incidentlab.llm.urllib.request.urlopen", side_effect=provider.urlopen):
            status, headers, result = asgi_request(
                "POST",
                "/v1/investigations",
                body={"incident_id": "checkout-latency-001"},
                headers={"x-request-id": "full-stack-check-001"},
            )
        after = METRICS.snapshot()

        self.assertEqual(status, 200)
        self.assertEqual(headers["x-request-id"], "full-stack-check-001")
        self.assertEqual(result["incident_id"], "checkout-latency-001")
        self.assertEqual(
            [item["name"] for item in result["tool_calls"]],
            ["query_metrics", "query_logs", "query_deployments", "retrieve_knowledge"],
        )
        self.assertTrue(
            any(str(item["source"]).startswith("knowledge:") for item in result["evidence"])
        )
        self.assertEqual(result["run"]["citation_validity"], 1.0)
        self.assertEqual(result["run"]["agent_steps"], 4)
        self.assertEqual(result["run"]["prompt_tokens"], 100)
        self.assertEqual(len(provider.requests), 5)
        self.assertTrue(
            all(
                item["response_format"] == {"type": "json_object"}
                for item in provider.requests
            )
        )
        self.assertEqual(after.investigations, before.investigations + 1)
        self.assertEqual(after.model_prompt_tokens, before.model_prompt_tokens + 100)

    def test_provider_failure_becomes_safe_503_response(self) -> None:
        with self.assertLogs("rootsignal.api", level="WARNING") as logs:
            with patch(
                "incidentlab.llm.urllib.request.urlopen",
                side_effect=urllib.error.URLError("model offline"),
            ):
                status, _, result = asgi_request(
                    "POST",
                    "/v1/investigations",
                    body={"incident_id": "checkout-latency-001"},
                )
        self.assertEqual(status, 503)
        self.assertEqual(result["error"]["code"], "service_unavailable")
        self.assertNotIn("model offline", json.dumps(result))
        self.assertIn("Model unavailable", logs.output[0])


if __name__ == "__main__":
    unittest.main()
