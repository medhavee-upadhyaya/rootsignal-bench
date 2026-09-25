from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

try:
    from incidentlab.api import InvestigationRequest, app
    from incidentlab.agent import Investigator
    from incidentlab.evidence_bundle import verify_evidence_bundle
    from incidentlab.fixtures import load_incident
    from incidentlab.http import RateLimiter, request_id
    from incidentlab.runs import RunStore
except (ImportError, RuntimeError):
    InvestigationRequest = None  # type: ignore[assignment,misc]


@unittest.skipIf(InvestigationRequest is None, "API dependencies are not installed")
class APITests(unittest.TestCase):
    def test_complete_suite_selects_latest_model_run_per_evaluable_incident(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            selected_ids = []
            for fixture_path in (
                "fixtures/incidents/checkout_latency.yaml",
                "fixtures/incidents/billing_clock.json",
            ):
                incident = load_incident(fixture_path)
                result = Investigator().investigate(incident).as_dict()
                store.save(
                    incident_id=incident.incident_id, incident_title=incident.title,
                    mode="model", model="older-model", query=incident.summary,
                    fixture_sha256="a" * 64, result=result, metadata={},
                )
                selected_ids.append(store.save(
                    incident_id=incident.incident_id, incident_title=incident.title,
                    mode="model", model="candidate-model", query=incident.summary,
                    fixture_sha256="a" * 64, result=result, metadata={},
                )["run_id"])

            with patch("incidentlab.api.RUNS", store):
                status, _, report = asgi_request("GET", "/v1/evaluation-suites/latest")

            self.assertEqual(status, 200)
            self.assertEqual(report["fixture_count"], 2)
            self.assertEqual(report["selection"]["strategy"], "latest_model_run_per_incident")
            self.assertEqual(set(report["selection"]["included_run_ids"]), set(selected_ids))
            self.assertTrue(report["integrity"]["digest"])

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
        self.assertEqual(record["metadata"]["knowledge_collections"], ["incident-runbooks"])
        self.assertEqual(record["result"]["root_cause"], result["root_cause"])

        status, _, history = asgi_request("GET", "/v1/runs")
        self.assertEqual(status, 200)
        self.assertIn(run_id, [run["run_id"] for run in history["runs"]])

    def test_human_review_is_appended_and_exported_without_mutating_result(self) -> None:
        _, _, result = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "checkout-latency-001"}
        )
        run_id = result["record"]["run_id"]
        root_cause = result["root_cause"]
        status, _, review = asgi_request(
            "POST",
            f"/v1/runs/{run_id}/reviews",
            body={"verdict": "needs_investigation", "note": "Confirm against database events"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(review["verdict"], "needs_investigation")

        _, _, stored = asgi_request("GET", f"/v1/runs/{run_id}")
        self.assertEqual(stored["result"]["root_cause"], root_cause)
        self.assertEqual(stored["reviews"], [review])
        _, _, bundle = asgi_request("GET", f"/v1/runs/{run_id}/export")
        self.assertEqual(bundle["run"]["reviews"], [review])
        self.assertTrue(verify_evidence_bundle(bundle))

    def test_human_review_rejects_credentials_before_persistence(self) -> None:
        _, _, result = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "checkout-latency-001"}
        )
        run_id = result["record"]["run_id"]
        credential = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
        status, _, payload = asgi_request(
            "POST",
            f"/v1/runs/{run_id}/reviews",
            body={"verdict": "rejected", "note": f"Leaked {credential}"},
        )
        self.assertEqual(status, 422)
        self.assertNotIn(credential, json.dumps(payload))
        _, _, stored = asgi_request("GET", f"/v1/runs/{run_id}")
        self.assertEqual(stored["reviews"], [])

    def test_run_history_filters_by_incident_mode_and_review(self) -> None:
        _, _, result = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "billing-clock-001"}
        )
        run_id = result["record"]["run_id"]
        asgi_request(
            "POST", f"/v1/runs/{run_id}/reviews", body={"verdict": "accepted"}
        )
        status, _, payload = asgi_request(
            "GET", "/v1/runs?incident_id=billing-clock-001&mode=baseline&review=accepted"
        )
        self.assertEqual(status, 200)
        self.assertIn(run_id, [item["run_id"] for item in payload["runs"]])
        self.assertEqual(
            payload["filters"],
            {"incident_id": "billing-clock-001", "mode": "baseline", "review": "accepted"},
        )
        self.assertEqual(
            next(item for item in payload["runs"] if item["run_id"] == run_id)["latest_review"],
            "accepted",
        )

        asgi_request("POST", f"/v1/runs/{run_id}/reviews", body={"verdict": "rejected"})
        _, _, payload = asgi_request(
            "GET", "/v1/runs?incident_id=billing-clock-001&mode=baseline&review=accepted"
        )
        self.assertNotIn(run_id, [item["run_id"] for item in payload["runs"]])
        _, _, payload = asgi_request(
            "GET", "/v1/runs?incident_id=billing-clock-001&mode=baseline&review=rejected"
        )
        self.assertIn(run_id, [item["run_id"] for item in payload["runs"]])

        status, _, payload = asgi_request("GET", "/v1/runs?mode=invalid")
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "validation_error")

    def test_run_export_is_downloadable_verifiable_and_oracle_free(self) -> None:
        _, _, reference = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "checkout-latency-001"}
        )
        _, _, candidate = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": "checkout-latency-001"}
        )
        run_id = reference["record"]["run_id"]
        candidate_id = candidate["record"]["run_id"]

        status, headers, bundle = asgi_request(
            "GET", f"/v1/runs/{run_id}/export?compare_to={candidate_id}"
        )

        self.assertEqual(status, 200)
        self.assertIn(f"rootsignal-{run_id}.json", headers["content-disposition"])
        self.assertTrue(verify_evidence_bundle(bundle))
        self.assertEqual(bundle["comparison"]["candidate"]["run"]["run_id"], candidate_id)
        self.assertNotIn('"oracle":', json.dumps(bundle).lower())

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

    def test_live_incident_requires_no_oracle_and_cannot_use_control(self) -> None:
        fixture = json.loads(
            Path("fixtures/incidents/checkout_latency.yaml").read_text(encoding="utf-8")
        )
        fixture["id"] = f"live-{uuid.uuid4().hex}"
        fixture["title"] = "Active checkout degradation"
        fixture["metadata"]["synthetic"] = False
        fixture["runbooks"] = []
        del fixture["oracle"]

        status, _, created = asgi_request("POST", "/v1/incidents", body=fixture)
        self.assertEqual(status, 201)
        self.assertFalse(created["incident"]["metadata"]["evaluable"])
        self.assertNotIn("oracle", json.dumps(created).lower())

        status, _, detail = asgi_request("GET", f"/v1/incidents/{fixture['id']}")
        self.assertEqual(status, 200)
        self.assertFalse(detail["metadata"]["evaluable"])
        self.assertIn("telemetry", detail)
        self.assertEqual(detail["runbooks"], [])

        status, _, rejected = asgi_request(
            "POST", "/v1/baselines/deterministic", body={"incident_id": fixture["id"]}
        )
        self.assertEqual(status, 409)
        self.assertIn("require a model investigation", rejected["error"]["message"])

    def test_incident_detail_exposes_observations_but_not_oracle(self) -> None:
        status, _, payload = asgi_request("GET", "/v1/incidents/checkout-latency-001")
        self.assertEqual(status, 200)
        self.assertIn("telemetry", payload)
        self.assertIn("runbooks", payload)
        self.assertNotIn("oracle", json.dumps(payload).lower())

        status, _, payload = asgi_request("GET", "/v1/incidents/missing")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_custom_incident_can_be_archived_without_breaking_historical_resolution(self) -> None:
        fixture = json.loads(
            Path("fixtures/incidents/checkout_latency.yaml").read_text(encoding="utf-8")
        )
        fixture["id"] = f"archive-{uuid.uuid4().hex}"
        status, _, _ = asgi_request("POST", "/v1/incidents", body=fixture)
        self.assertEqual(status, 201)

        status, _, archived = asgi_request("DELETE", f"/v1/incidents/{fixture['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(archived["status"], "archived")

        _, _, catalog = asgi_request("GET", "/v1/incidents")
        self.assertNotIn(fixture["id"], [item["id"] for item in catalog["incidents"]])
        status, _, detail = asgi_request("GET", f"/v1/incidents/{fixture['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["id"], fixture["id"])

    def test_built_in_incident_cannot_be_archived(self) -> None:
        status, _, payload = asgi_request("DELETE", "/v1/incidents/checkout-latency-001")
        self.assertEqual(status, 409)
        self.assertIn("cannot be archived", payload["error"]["message"])

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

    def test_both_execution_modes_reject_unknown_knowledge_scope(self) -> None:
        request = {
            "incident_id": "checkout-latency-001",
            "collection_ids": ["collection-that-does-not-exist"],
        }
        for path in ("/v1/baselines/deterministic", "/v1/investigations"):
            status, _, payload = asgi_request("POST", path, body=request)
            self.assertEqual(status, 422)
            self.assertEqual(payload["error"]["code"], "validation_error")
            self.assertIn("Unknown knowledge collections", payload["error"]["message"])

    def test_secret_bearing_knowledge_is_rejected_before_persistence(self) -> None:
        credential = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
        status, _, payload = asgi_request(
            "POST",
            "/v1/knowledge",
            body={
                "collection_id": "incident-runbooks",
                "source": "runbook/unsafe",
                "text": f"This document accidentally contains {credential} and must be rejected.",
            },
        )
        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertNotIn(credential, json.dumps(payload))

    def test_secret_bearing_custom_incident_is_rejected_before_persistence(self) -> None:
        credential = "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890"
        fixture = json.loads(
            Path("fixtures/incidents/checkout_latency.yaml").read_text(encoding="utf-8")
        )
        fixture["id"] = f"unsafe-{uuid.uuid4().hex}"
        fixture["telemetry"]["logs"].append(f"Accidental credential {credential}")

        status, _, payload = asgi_request("POST", "/v1/incidents", body=fixture)

        self.assertEqual(status, 422)
        self.assertEqual(payload["error"]["code"], "validation_error")
        self.assertNotIn(credential, json.dumps(payload))

    def test_secret_bearing_investigation_question_is_rejected_before_execution(self) -> None:
        credential = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
        for path in ("/v1/investigations", "/v1/baselines/deterministic"):
            status, _, payload = asgi_request(
                "POST",
                path,
                body={
                    "incident_id": "checkout-latency-001",
                    "query": f"Investigate using {credential}",
                },
            )
            self.assertEqual(status, 422)
            self.assertEqual(payload["error"]["code"], "validation_error")
            self.assertNotIn(credential, json.dumps(payload))

    def test_custom_investigation_question_is_trimmed_and_persisted(self) -> None:
        question = "Compare deployment changes with connection-pool saturation"
        status, _, result = asgi_request(
            "POST",
            "/v1/baselines/deterministic",
            body={"incident_id": "checkout-latency-001", "query": f"  {question}  "},
        )
        self.assertEqual(status, 200)
        status, _, stored = asgi_request("GET", f"/v1/runs/{result['record']['run_id']}")
        self.assertEqual(status, 200)
        self.assertEqual(stored["query"], question)

    def test_system_describes_honest_execution_modes(self) -> None:
        status, _, payload = asgi_request("GET", "/v1/system")
        self.assertEqual(status, 200)
        self.assertTrue(payload["execution_modes"]["baseline"]["oracle_backed"])
        self.assertFalse(payload["execution_modes"]["model"]["oracle_backed"])
        self.assertEqual(payload["llm"]["configuration"]["endpoint_env"], "INCIDENTLAB_LLM_URL")
        self.assertIn(payload["llm"]["status"], {"ready", "server_error", "incompatible_server", "model_not_loaded", "server_unreachable"})
        self.assertTrue(payload["llm"]["message"])
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

    def test_execution_budgets_are_bounded_and_persisted(self) -> None:
        for field, value in (("max_steps", 5), ("max_completion_tokens", 1001)):
            status, _, payload = asgi_request(
                "POST",
                "/v1/baselines/deterministic",
                body={"incident_id": "checkout-latency-001", field: value},
            )
            self.assertEqual(status, 422)
            self.assertEqual(payload["error"]["code"], "validation_error")

        status, _, result = asgi_request(
            "POST",
            "/v1/baselines/deterministic",
            body={
                "incident_id": "checkout-latency-001",
                "max_steps": 2,
                "max_completion_tokens": 128,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(result["tool_calls"]), 2)
        _, _, stored = asgi_request("GET", f"/v1/runs/{result['record']['run_id']}")
        self.assertEqual(
            stored["metadata"]["execution_budget"],
            {"max_steps": 2, "max_completion_tokens": 128},
        )

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
    status, response_headers, response_body = asgi_raw_request(method, path, body, headers)
    return status, response_headers, json.loads(response_body or b"{}")


def asgi_raw_request(
    method: str,
    path: str,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    target = urlsplit(path)
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
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": target.path,
        "raw_path": target.path.encode(),
        "query_string": target.query.encode(),
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
    return int(start["status"]), response_headers, response_body


if __name__ == "__main__":
    unittest.main()
