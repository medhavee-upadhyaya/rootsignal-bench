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
ReviewVerdict = Literal["accepted", "rejected", "needs_investigation"]


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
                CREATE TABLE IF NOT EXISTS run_reviews (
                    review_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    verdict TEXT NOT NULL CHECK(verdict IN ('accepted', 'rejected', 'needs_investigation')),
                    note TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES experiment_runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_run_reviews_run
                    ON run_reviews(run_id, created_at, review_id);
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

    def list(
        self,
        limit: int = 20,
        cursor: str | None = None,
        incident_id: str | None = None,
        mode: ExecutionMode | None = None,
        review: ReviewVerdict | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 101)
        with self._connect() as connection:
            boundary = None
            if cursor:
                boundary = connection.execute(
                    "SELECT created_at, run_id FROM experiment_runs WHERE run_id = ?", (cursor,)
                ).fetchone()
                if boundary is None:
                    raise ValueError("Unknown run cursor")
            conditions: list[str] = []
            parameters: list[object] = []
            if boundary:
                conditions.append("(created_at < ? OR (created_at = ? AND run_id < ?))")
                parameters.extend([boundary["created_at"], boundary["created_at"], boundary["run_id"]])
            if incident_id:
                conditions.append("incident_id = ?")
                parameters.append(incident_id)
            if mode:
                conditions.append("mode = ?")
                parameters.append(mode)
            if review:
                conditions.append(
                    "EXISTS (SELECT 1 FROM run_reviews rr WHERE rr.run_id = experiment_runs.run_id AND rr.verdict = ?)"
                )
                parameters.append(review)
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            rows = connection.execute(
                """
                SELECT run_id, created_at, incident_id, incident_title, mode, model,
                       fixture_sha256, result_json, metadata_json
                FROM experiment_runs
                """ + where + " ORDER BY created_at DESC, run_id DESC LIMIT ?",
                (*parameters, safe_limit),
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
        record["reviews"] = self.reviews(run_id)
        return record

    def latest_model_runs_by_incident(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the newest model run for each incident across the complete store."""
        safe_limit = min(max(limit, 1), 50)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id FROM (
                    SELECT run_id, created_at, rowid AS run_rowid,
                           ROW_NUMBER() OVER (
                               PARTITION BY incident_id
                               ORDER BY created_at DESC, rowid DESC
                           ) AS incident_rank
                    FROM experiment_runs
                    WHERE mode = 'model'
                )
                WHERE incident_rank = 1
                ORDER BY created_at DESC, run_rowid DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        records = [self.get(str(row["run_id"])) for row in rows]
        return [record for record in records if record is not None]

    def add_review(self, run_id: str, verdict: ReviewVerdict, note: str = "") -> dict[str, str]:
        review_id = uuid.uuid4().hex
        created_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM experiment_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if exists is None:
                raise ValueError("Unknown run")
            connection.execute(
                "INSERT INTO run_reviews VALUES (?, ?, ?, ?, ?)",
                (review_id, run_id, created_at, verdict, note),
            )
        return {
            "review_id": review_id,
            "run_id": run_id,
            "created_at": created_at,
            "verdict": verdict,
            "note": note,
        }

    def reviews(self, run_id: str) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT review_id, run_id, created_at, verdict, note FROM run_reviews
                WHERE run_id = ? ORDER BY created_at, rowid
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

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
            "evaluable": metadata.get("evaluable", True),
        }
