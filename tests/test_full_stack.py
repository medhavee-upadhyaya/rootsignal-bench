from __future__ import annotations

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

try:
    from incidentlab.api import METRICS
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
