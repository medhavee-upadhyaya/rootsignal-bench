from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

ExecutionMode = Literal["baseline", "model"]


class RunStore:
    """Durable experiment records stored as immutable JSON snapshots."""

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
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    incident_id TEXT NOT NULL,
                    incident_title TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('baseline', 'model')),
                    model TEXT NOT NULL,
                    query TEXT NOT NULL,
                    fixture_sha256 TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_experiment_runs_created
                    ON experiment_runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_experiment_runs_incident
                    ON experiment_runs(incident_id, created_at DESC);
                """
            )

    def save(
        self,
        *,
        incident_id: str,
        incident_title: str,
        mode: ExecutionMode,
        model: str,
        query: str,
        fixture_sha256: str,
        result: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        created_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO experiment_runs(
                    run_id, created_at, incident_id, incident_title, mode, model,
                    query, fixture_sha256, result_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    created_at,
                    incident_id,
                    incident_title,
                    mode,
                    model,
                    query,
                    fixture_sha256,
                    json.dumps(result, sort_keys=True, separators=(",", ":")),
                    json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                ),
            )
        return {"run_id": run_id, "created_at": created_at, "mode": mode}

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 100)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, created_at, incident_id, incident_title, mode, model,
                       fixture_sha256, result_json, metadata_json
                FROM experiment_runs ORDER BY created_at DESC, run_id DESC LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM experiment_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        record = self._summary(row)
        record["query"] = row["query"]
        record["result"] = json.loads(row["result_json"])
        record["metadata"] = json.loads(row["metadata_json"])
        return record

    @staticmethod
    def _summary(row: sqlite3.Row) -> dict[str, Any]:
        result = json.loads(row["result_json"])
        metadata = json.loads(row["metadata_json"])
        return {
            "run_id": row["run_id"],
            "created_at": row["created_at"],
            "incident_id": row["incident_id"],
            "incident_title": row["incident_title"],
            "mode": row["mode"],
            "model": row["model"],
            "fixture_sha256": row["fixture_sha256"],
            "confidence": result.get("confidence", 0),
            "tool_calls": len(result.get("tool_calls", [])),
            "evidence_items": len(result.get("evidence", [])),
            "latency_ms": metadata.get("latency_ms", 0),
        }
