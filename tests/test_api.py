from __future__ import annotations

import asyncio
import json
import unittest

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

    def test_incident_catalog_is_public_and_complete(self) -> None:
        status, _, payload = asgi_request("GET", "/v1/incidents")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 26)
        self.assertEqual(len(payload["incidents"]), 26)
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

    def test_incident_detail_exposes_observations_but_not_oracle(self) -> None:
        status, _, payload = asgi_request("GET", "/v1/incidents/checkout-latency-001")
        self.assertEqual(status, 200)
        self.assertIn("telemetry", payload)
        self.assertIn("runbooks", payload)
        self.assertNotIn("oracle", json.dumps(payload).lower())

        status, _, payload = asgi_request("GET", "/v1/incidents/missing")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

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
