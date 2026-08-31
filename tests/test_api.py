from __future__ import annotations

import asyncio
import json
import unittest
import uuid
from pathlib import Path

try:
    from incidentlab.api import InvestigationRequest, app
    from incidentlab.http import RateLimiter, request_id
except (ImportError, RuntimeError):
    InvestigationRequest = None  # type: ignore[assignment,misc]


@unittest.skipIf(InvestigationRequest is None, "API dependencies are not installed")
class APITests(unittest.TestCase):
    def test_investigation_resolves_declared_fixture_id(self) -> None:
        status, _, response = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "checkout-latency-001"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["incident_id"], "checkout-latency-001")
        self.assertRegex(response["record"]["run_id"], r"^[a-f0-9]{32}$")

    def test_unknown_incident_is_404(self) -> None:
        status, _, _ = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "missing"}
        )
        self.assertEqual(status, 404)

    def test_completed_run_is_available_in_history(self) -> None:
        status, _, result = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "billing-clock-001"}
        )
        self.assertEqual(status, 200)
        run_id = result["record"]["run_id"]

        status, _, record = asgi_request("GET", f"/v1/runs/{run_id}")
        self.assertEqual(status, 200)
        self.assertEqual(record["incident_id"], "billing-clock-001")
        self.assertEqual(record["mode"], "baseline")
        self.assertTrue(record["metadata"]["oracle_backed"])
        self.assertEqual(record["result"]["root_cause"], result["root_cause"])

        status, _, history = asgi_request("GET", "/v1/runs")
        self.assertEqual(status, 200)
        self.assertIn(run_id, [run["run_id"] for run in history["runs"]])

    def test_comparison_rejects_identical_runs(self) -> None:
        status, _, result = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "checkout-latency-001"}
        )
        self.assertEqual(status, 200)
        run_id = result["record"]["run_id"]
        status, _, payload = asgi_request(
            "POST",
            "/v1/comparisons",
            body={"reference_run_id": run_id, "candidate_run_id": run_id},
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "comparison_conflict")

    def test_incident_catalog_is_public_and_complete(self) -> None:
        status, _, payload = asgi_request("GET", "/v1/incidents")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(payload["count"], 26)
        self.assertEqual(
            sum(item["metadata"]["catalog_source"] == "built-in" for item in payload["incidents"]),
            26,
        )
        self.assertEqual(
            [incident["id"] for incident in payload["incidents"]],
            sorted(incident["id"] for incident in payload["incidents"]),
        )
        self.assertNotIn("oracle", json.dumps(payload).lower())
        checkout = next(
            incident for incident in payload["incidents"] if incident["id"] == "checkout-latency-001"
        )
        self.assertEqual(checkout["metadata"]["failure_class"], "database-saturation")
        self.assertEqual(checkout["observation_counts"]["metrics"], 4)

    def test_custom_incident_is_created_without_exposing_oracle(self) -> None:
        fixture = json.loads(
            Path("fixtures/incidents/checkout_latency.yaml").read_text(encoding="utf-8")
        )
        fixture["id"] = f"custom-{uuid.uuid4().hex}"
        fixture["title"] = "Custom checkout investigation"
        status, _, created = asgi_request("POST", "/v1/incidents", body=fixture)
        self.assertEqual(status, 201)
        self.assertEqual(created["incident"]["metadata"]["catalog_source"], "custom")
        self.assertNotIn("oracle", json.dumps(created).lower())

        status, _, result = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": fixture["id"]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["incident_id"], fixture["id"])
        self.assertNotEqual(result["record"]["run_id"], "")

    def test_incident_detail_exposes_observations_but_not_oracle(self) -> None:
        status, _, payload = asgi_request("GET", "/v1/incidents/checkout-latency-001")
        self.assertEqual(status, 200)
        self.assertIn("telemetry", payload)
        self.assertIn("runbooks", payload)
        self.assertNotIn("oracle", json.dumps(payload).lower())

        status, _, payload = asgi_request("GET", "/v1/incidents/missing")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_knowledge_collection_can_be_created_listed_and_indexed(self) -> None:
        collection_id = f"team-{uuid.uuid4().hex}"
        status, _, created = asgi_request(
            "POST",
            "/v1/knowledge/collections",
            body={"id": collection_id, "name": "Team operations"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["id"], collection_id)

        status, _, indexed = asgi_request(
            "POST",
            "/v1/knowledge",
            body={
                "collection_id": collection_id,
                "source": "runbook/team",
                "text": f"A sufficiently detailed operational procedure for team {collection_id}.",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(indexed["collection_id"], collection_id)
        self.assertGreater(indexed["chunks"], 0)

        status, _, catalog = asgi_request("GET", "/v1/knowledge/collections")
        self.assertEqual(status, 200)
        collection = next(item for item in catalog["collections"] if item["id"] == collection_id)
        self.assertEqual(collection["documents"], 1)

    def test_system_describes_honest_execution_modes(self) -> None:
        status, _, payload = asgi_request("GET", "/v1/system")
        self.assertEqual(status, 200)
        self.assertTrue(payload["execution_modes"]["baseline"]["oracle_backed"])
        self.assertFalse(payload["execution_modes"]["model"]["oracle_backed"])
        self.assertEqual(payload["llm"]["configuration"]["endpoint_env"], "INCIDENTLAB_LLM_URL")
        self.assertNotIn("base_url", payload["llm"])
        self.assertIn("search_runbooks", payload["tools"])

    def test_request_id_is_echoed_in_success_and_structured_error(self) -> None:
        correlation_id = "incident-checkout-42"
        status, headers, _ = asgi_request("GET", "/healthz", headers={"x-request-id": correlation_id})
        self.assertEqual(status, 200)
        self.assertEqual(headers["x-request-id"], correlation_id)
        self.assertEqual(headers["x-content-type-options"], "nosniff")

        status, _, payload = asgi_request(
            "POST",
            "/v1/baselines/deterministic",
            body={"incident_id": "missing"},
            headers={"x-request-id": correlation_id},
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertEqual(payload["error"]["request_id"], correlation_id)

    def test_validation_errors_do_not_expose_framework_details(self) -> None:
        status, _, payload = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "invalid id!"}
        )
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertNotIn("input", payload)

    def test_request_id_rejects_header_injection(self) -> None:
        generated = request_id("unsafe value")
        self.assertRegex(generated, r"^[a-f0-9]{32}$")

    def test_rate_limiter_expires_requests(self) -> None:
        now = [100.0]
        limiter = RateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
        self.assertEqual(limiter.allow("client")[:2], (True, 1))
        self.assertEqual(limiter.allow("client")[:2], (True, 0))
        self.assertFalse(limiter.allow("client")[0])
        now[0] = 111.0
        self.assertTrue(limiter.allow("client")[0])


def asgi_request(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], dict[str, object]]:
    encoded = json.dumps(body).encode() if body is not None else b""
    request_headers = {"host": "test", **(headers or {})}
    if body is not None:
        request_headers["content-type"] = "application/json"
    messages: list[dict[str, object]] = []
    received = False

    async def receive() -> dict[str, object]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": encoded, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(key.lower().encode(), value.encode()) for key, value in request_headers.items()],
        "client": ("testclient", 50000),
        "server": ("test", 80),
    }
    asyncio.run(app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_headers = {
        key.decode().lower(): value.decode() for key, value in start.get("headers", [])
    }
    response_body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return int(start["status"]), response_headers, json.loads(response_body or b"{}")


if __name__ == "__main__":
    unittest.main()
