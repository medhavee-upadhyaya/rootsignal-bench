from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Incident


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip("'\"")


def _minimal_yaml(text: str) -> dict[str, Any]:
    """Parse our JSON-compatible fixtures when PyYAML is unavailable."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Install PyYAML for non-JSON YAML fixtures") from exc


def load_incident(path: str | Path) -> Incident:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]

        data = yaml.safe_load(text)
    except ImportError:
        data = _minimal_yaml(text)
    validate_fixture(data)
    return Incident(
        incident_id=data["id"],
        title=data["title"],
        summary=data["summary"],
        telemetry=data["telemetry"],
        runbooks=data.get("runbooks", []),
        oracle=data["oracle"],
    )


def validate_fixture(data: dict[str, Any]) -> None:
    required = {"id", "title", "summary", "telemetry", "oracle"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Fixture is missing required fields: {sorted(missing)}")
    oracle_required = {"root_cause", "required_evidence", "remediation", "expected_tools"}
    missing_oracle = oracle_required - data["oracle"].keys()
    if missing_oracle:
        raise ValueError(f"Oracle is missing required fields: {sorted(missing_oracle)}")
