from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from incidentlab.evidence_bundle import build_evidence_bundle, main, verify_evidence_bundle
from incidentlab.fixtures import load_incident
from incidentlab.runs import RunStore


class EvidenceBundleTests(unittest.TestCase):
    def test_bundle_is_portable_oracle_free_and_tamper_evident(self) -> None:
        incident = load_incident(Path("fixtures/incidents/checkout_latency.yaml"))
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            reference = store.save(
                incident_id=incident.incident_id,
                incident_title=incident.title,
                mode="baseline",
                model="deterministic-v1",
                query=incident.summary,
                fixture_sha256="a" * 64,
                result=_result_payload(incident),
                metadata={"latency_ms": 12, "request_id": "request-1", "oracle_backed": True},
            )
            run = store.get(reference["run_id"])
            assert run is not None
            bundle = build_evidence_bundle(incident, run)

        serialized = json.dumps(bundle)
        self.assertTrue(verify_evidence_bundle(json.loads(serialized)))
        self.assertNotIn('"oracle":', serialized.lower())
        self.assertTrue(bundle["run"]["metadata"]["oracle_backed"])
        self.assertEqual(bundle["scorecard"]["overall"], 1.0)

        bundle["run"]["result"]["root_cause"] = "tampered diagnosis"
        self.assertFalse(verify_evidence_bundle(bundle))

    def test_exported_file_can_be_verified_offline(self) -> None:
        incident = load_incident(Path("fixtures/incidents/checkout_latency.yaml"))
        with tempfile.TemporaryDirectory() as directory:
            store = RunStore(Path(directory) / "runs.db")
            reference = store.save(
                incident_id=incident.incident_id,
                incident_title=incident.title,
                mode="baseline",
                model="deterministic-v1",
                query=incident.summary,
                fixture_sha256="b" * 64,
                result=_result_payload(incident),
                metadata={"latency_ms": 9, "oracle_backed": True},
            )
            run = store.get(reference["run_id"])
            assert run is not None
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(build_evidence_bundle(incident, run)))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(path)]), 0)

            payload = json.loads(path.read_text())
            payload["run"]["model"] = "substituted-model"
            path.write_text(json.dumps(payload))
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(path)]), 1)


def _result_payload(incident) -> dict[str, object]:
    return {
        "incident_id": incident.incident_id,
        "root_cause": incident.oracle["root_cause"],
        "confidence": 1.0,
        "evidence": [
            {"source": "metrics", "content": item, "relevance": 1.0}
            for item in incident.oracle["required_evidence"]
        ],
        "remediation": incident.oracle["remediation"],
        "tool_calls": [
            {"name": name, "arguments": {}} for name in incident.oracle["expected_tools"]
        ],
        "limitations": [],
    }
