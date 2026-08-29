from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .fixtures import incident_from_dict, validate_fixture
from .models import Incident

MAX_FIXTURE_BYTES = 1_000_000
SUPPORTED_TOOLS = {
    "query_metrics",
    "query_logs",
    "query_deployments",
    "search_runbooks",
}


def validate_custom_fixture(fixture: dict[str, Any]) -> None:
    serialized = json.dumps(fixture, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode()) > MAX_FIXTURE_BYTES:
        raise ValueError("Fixture must not exceed 1 MB")
    validate_fixture(fixture)
    expected_tools = set(fixture["oracle"]["expected_tools"])
    unsupported = sorted(expected_tools - SUPPORTED_TOOLS)
    if unsupported:
        raise ValueError(f"Unsupported expected tools: {unsupported}")


class CustomIncidentStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS custom_incidents (
                    incident_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    fixture_sha256 TEXT NOT NULL,
                    fixture_json TEXT NOT NULL
                );
                """
            )

    def save(self, fixture: dict[str, Any]) -> dict[str, str]:
        validate_custom_fixture(fixture)
        serialized = json.dumps(fixture, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        created_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO custom_incidents VALUES (?, ?, ?, ?)",
                    (fixture["id"], created_at, digest, serialized),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Incident id already exists") from exc
        return {"incident_id": fixture["id"], "created_at": created_at, "fixture_sha256": digest}

    def get(self, incident_id: str) -> Incident | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT fixture_json FROM custom_incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        return incident_from_dict(json.loads(row["fixture_json"])) if row else None

    def digest(self, incident_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT fixture_sha256 FROM custom_incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        return str(row["fixture_sha256"]) if row else None

    def list(self) -> list[Incident]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT fixture_json FROM custom_incidents ORDER BY created_at, incident_id"
            ).fetchall()
        return [incident_from_dict(json.loads(row["fixture_json"])) for row in rows]
