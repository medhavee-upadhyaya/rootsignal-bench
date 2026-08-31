from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .comparison import compare_runs
from .evaluation import score
from .models import Evidence, Incident, InvestigationResult, ToolCall


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _result(payload: dict[str, Any]) -> InvestigationResult:
    return InvestigationResult(
        incident_id=str(payload["incident_id"]),
        root_cause=str(payload["root_cause"]),
        confidence=float(payload.get("confidence", 0)),
        evidence=[Evidence(**item) for item in payload.get("evidence", [])],
        remediation=[str(item) for item in payload.get("remediation", [])],
        tool_calls=[ToolCall(**item) for item in payload.get("tool_calls", [])],
        limitations=[str(item) for item in payload.get("limitations", [])],
    )


def build_evidence_bundle(
    incident: Incident,
    run: dict[str, Any],
    comparison_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema_version": "1.0",
        "exported_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "run": run,
        "scorecard": score(incident, _result(run["result"])).as_dict(),
        "comparison": None,
    }
    if comparison_run is not None:
        artifact["comparison"] = compare_runs(incident, run, comparison_run)
    digest = hashlib.sha256(_canonical(artifact)).hexdigest()
    return {
        **artifact,
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-compact-utf8",
            "digest": digest,
        },
    }


def verify_evidence_bundle(bundle: dict[str, Any]) -> bool:
    integrity = bundle.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        return False
    artifact = {key: value for key, value in bundle.items() if key != "integrity"}
    actual = hashlib.sha256(_canonical(artifact)).hexdigest()
    return actual == integrity.get("digest")


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    if len(arguments) != 1:
        print("usage: python -m incidentlab.evidence_bundle <bundle.json>", file=sys.stderr)
        return 2
    try:
        payload = json.loads(Path(arguments[0]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid evidence bundle: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict) or not verify_evidence_bundle(payload):
        print("integrity verification failed", file=sys.stderr)
        return 1
    print(f"verified sha256 {payload['integrity']['digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
