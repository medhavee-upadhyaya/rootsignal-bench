from __future__ import annotations

import json
from typing import Any


def _string_rows(value: object, label: str, minimum: int) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        suffix = "" if minimum == 1 else "s"
        raise ValueError(f"{label} must contain at least {minimum} item{suffix}")
    return [item if isinstance(item, str) else json.dumps(item, sort_keys=True) for item in value]


def normalize_telemetry_intake(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a compact external telemetry envelope into a live incident fixture."""
    if "oracle" in payload:
        raise ValueError("Telemetry intake accepts observations only; use fixture import for evaluations")
    telemetry = payload.get("telemetry", payload)
    if not isinstance(telemetry, dict):
        raise ValueError("Telemetry must be an object")
    metrics = telemetry.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("Metrics must contain at least one signal")
    logs = _string_rows(telemetry.get("logs"), "Logs", 2)
    deployments = _string_rows(telemetry.get("deployments"), "Deployments", 1)
    runbooks = payload.get("runbooks", [])
    if not isinstance(runbooks, list):
        raise ValueError("Runbooks must be a list")
    difficulty = payload.get("difficulty", "medium")
    if difficulty not in {"easy", "medium", "hard"}:
        raise ValueError("Difficulty must be easy, medium, or hard")
    return {
        "schema_version": "1.0",
        "id": payload.get("id", ""),
        "title": payload.get("title", ""),
        "summary": payload.get("summary", ""),
        "metadata": {
            "failure_class": payload.get("failure_class", "live-incident"),
            "difficulty": difficulty,
            "license": "Proprietary",
            "synthetic": False,
            "intake": "telemetry-api",
        },
        "telemetry": {"metrics": metrics, "logs": logs, "deployments": deployments},
        "runbooks": runbooks,
    }
