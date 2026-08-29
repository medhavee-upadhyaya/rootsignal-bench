from __future__ import annotations

import json
import re
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
    return incident_from_dict(data)


def incident_from_dict(data: dict[str, Any]) -> Incident:
    validate_fixture(data)
    return Incident(
        incident_id=data["id"],
        title=data["title"],
        summary=data["summary"],
        telemetry=data["telemetry"],
        runbooks=data.get("runbooks", []),
        oracle=data["oracle"],
        metadata=data["metadata"],
    )


def validate_fixture(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("Fixture must be an object")
    required = {"schema_version", "id", "title", "summary", "telemetry", "runbooks", "oracle", "metadata"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Fixture is missing required fields: {sorted(missing)}")
    if data["schema_version"] != "1.0":
        raise ValueError("Fixture schema_version must be 1.0")
    if not re.fullmatch(r"[a-z0-9-]+", str(data["id"])):
        raise ValueError("Fixture id must use lowercase letters, digits, and hyphens")
    for field_name in ("title", "summary"):
        if not isinstance(data[field_name], str) or not data[field_name].strip():
            raise ValueError(f"Fixture {field_name} must be a non-empty string")
    telemetry = data["telemetry"]
    if not isinstance(telemetry, dict):
        raise ValueError("Fixture telemetry must be an object")
    if not isinstance(telemetry.get("metrics"), dict) or not telemetry["metrics"]:
        raise ValueError("Fixture telemetry requires non-empty metrics")
    if not isinstance(telemetry.get("logs"), list) or len(telemetry["logs"]) < 2:
        raise ValueError("Fixture telemetry requires at least two log events")
    if not isinstance(telemetry.get("deployments"), list) or not telemetry["deployments"]:
        raise ValueError("Fixture telemetry requires deployment history")
    runbooks = data["runbooks"]
    if not isinstance(runbooks, list) or not runbooks:
        raise ValueError("Fixture requires at least one runbook")
    runbook_ids = [item.get("id") for item in runbooks if isinstance(item, dict)]
    if len(runbook_ids) != len(runbooks) or len(set(runbook_ids)) != len(runbook_ids):
        raise ValueError("Fixture runbook ids must be present and unique")
    for runbook in runbooks:
        if not all(isinstance(runbook.get(key), str) and runbook[key].strip() for key in ("id", "title", "content")):
            raise ValueError("Every runbook requires a non-empty id, title, and content")
    oracle_required = {"root_cause", "required_evidence", "remediation", "expected_tools"}
    missing_oracle = oracle_required - data["oracle"].keys()
    if missing_oracle:
        raise ValueError(f"Oracle is missing required fields: {sorted(missing_oracle)}")
    if not isinstance(data["oracle"]["root_cause"], str) or not data["oracle"]["root_cause"].strip():
        raise ValueError("Oracle root_cause must be a non-empty string")
    for field_name in ("required_evidence", "remediation", "expected_tools"):
        value = data["oracle"][field_name]
        if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError(f"Oracle {field_name} must be a non-empty string list")
    metadata = data["metadata"]
    metadata_required = {"failure_class", "difficulty", "license", "synthetic"}
    if not isinstance(metadata, dict) or metadata_required - metadata.keys():
        raise ValueError(f"Fixture metadata requires {sorted(metadata_required)}")
    if metadata["difficulty"] not in {"easy", "medium", "hard"}:
        raise ValueError("Fixture difficulty must be easy, medium, or hard")
    if metadata["synthetic"] is not True:
        raise ValueError("Public fixtures must explicitly declare synthetic=true")
