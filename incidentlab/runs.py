from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

ExecutionMode = Literal["baseline", "model"]
ReviewVerdict = Literal["accepted", "rejected", "needs_investigation"]
ReviewFilter = Literal["accepted", "rejected", "needs_investigation", "unreviewed"]


class WorkflowConflictError(ValueError):
    """Raised when a workflow idempotency key cannot be safely reused."""


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
                CREATE TABLE IF NOT EXISTS workflow_requests (
                    workflow_id TEXT PRIMARY KEY,
                    request_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    run_id TEXT,
                    FOREIGN KEY(run_id) REFERENCES experiment_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS integration_jobs (
                    job_id TEXT PRIMARY KEY,
                    request_sha256 TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    run_id TEXT,
                    error_code TEXT,
                    FOREIGN KEY(run_id) REFERENCES experiment_runs(run_id)
                );
                """
            )
            job_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(integration_jobs)")
            }
            if "request_json" not in job_columns:
                connection.execute(
                    "ALTER TABLE integration_jobs ADD COLUMN request_json TEXT NOT NULL DEFAULT '{}'"
                )

    def enqueue_job(
        self, job_id: str, request_sha256: str, request_payload: dict[str, Any]
    ) -> dict[str, str]:
        created_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO integration_jobs(
                    job_id, request_sha256, request_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', ?, ?)
                """,
                (
                    job_id,
                    request_sha256,
                    json.dumps(request_payload, sort_keys=True, separators=(",", ":")),
                    created_at,
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM integration_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        assert row is not None
        if row["request_sha256"] != request_sha256:
            raise WorkflowConflictError("Integration job id already has different inputs")
        return self._job_record(row)

    def get_job_request(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_json FROM integration_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return json.loads(row["request_json"]) if row is not None else None

    def claim_job(self, job_id: str, *, lease_seconds: int = 900) -> bool:
        now = datetime.now(UTC)
        updated_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, updated_at FROM integration_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None or row["status"] == "completed":
                return False
            stale = row["status"] == "running" and now >= datetime.fromisoformat(
                str(row["updated_at"]).replace("Z", "+00:00")
            ) + timedelta(seconds=lease_seconds)
            if row["status"] not in {"queued", "failed"} and not stale:
                return False
            cursor = connection.execute(
                """
                UPDATE integration_jobs SET status = 'running', updated_at = ?, error_code = NULL
                WHERE job_id = ? AND status = ? AND updated_at = ?
                """,
                (updated_at, job_id, row["status"], row["updated_at"]),
            )
            return cursor.rowcount == 1

    def finish_job(self, job_id: str, *, run_id: str | None, error_code: str | None = None) -> None:
        status = "completed" if run_id else "failed"
        updated_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE integration_jobs
                SET status = ?, updated_at = ?, run_id = ?, error_code = ?
                WHERE job_id = ? AND status = 'running'
                """,
                (status, updated_at, run_id, error_code, job_id),
            )

    def get_job(self, job_id: str) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM integration_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._job_record(row) if row is not None else None

    @staticmethod
    def _job_record(row: sqlite3.Row) -> dict[str, str]:
        result = {
            "job_id": str(row["job_id"]),
            "status": str(row["status"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        if row["run_id"]:
            result["run_id"] = str(row["run_id"])
        if row["error_code"]:
            result["error_code"] = str(row["error_code"])
        return result

    def claim_workflow(
        self,
        workflow_id: str,
        request_sha256: str,
        *,
        lease_seconds: int = 900,
        now: datetime | None = None,
    ) -> dict[str, str]:
        claimed_at = now or datetime.now(UTC)
        created_at = claimed_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO workflow_requests VALUES (?, ?, ?, NULL)",
                    (workflow_id, request_sha256, created_at),
                )
                return {"status": "claimed", "created_at": created_at}
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT request_sha256, created_at, run_id FROM workflow_requests WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone()
                if row is None or row["request_sha256"] != request_sha256:
                    raise WorkflowConflictError(
                        "Workflow id already exists with different inputs"
                    )
                if row["run_id"] is None:
                    previous_claim = datetime.fromisoformat(
                        str(row["created_at"]).replace("Z", "+00:00")
                    )
                    if claimed_at >= previous_claim + timedelta(seconds=lease_seconds):
                        cursor = connection.execute(
                            """
                            UPDATE workflow_requests SET created_at = ?
                            WHERE workflow_id = ? AND request_sha256 = ?
                                AND created_at = ? AND run_id IS NULL
                            """,
                            (created_at, workflow_id, request_sha256, row["created_at"]),
                        )
                        if cursor.rowcount == 1:
                            return {"status": "reclaimed", "created_at": created_at}
                    return {"status": "in_progress", "created_at": str(row["created_at"])}
                return {
                    "status": "completed", "created_at": str(row["created_at"]),
                    "run_id": str(row["run_id"]),
                }

    def get_workflow(self, workflow_id: str) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT created_at, run_id FROM workflow_requests WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        if row is None:
            return None
        result = {
            "workflow_id": workflow_id,
            "status": "completed" if row["run_id"] else "in_progress",
            "created_at": str(row["created_at"]),
        }
        if row["run_id"]:
            result["run_id"] = str(row["run_id"])
        return result

    def complete_workflow(self, workflow_id: str, run_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE workflow_requests SET run_id = ? WHERE workflow_id = ? AND run_id IS NULL",
                (run_id, workflow_id),
            )
        if cursor.rowcount != 1:
            raise WorkflowConflictError("Workflow request is not pending")

    def release_workflow(self, workflow_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM workflow_requests WHERE workflow_id = ? AND run_id IS NULL",
                (workflow_id,),
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
        review: ReviewFilter | None = None,
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
                if review == "unreviewed":
                    conditions.append(
                        "NOT EXISTS (SELECT 1 FROM run_reviews rr WHERE rr.run_id = experiment_runs.run_id)"
                    )
                else:
                    conditions.append(
                        """(SELECT rr.verdict FROM run_reviews rr
                            WHERE rr.run_id = experiment_runs.run_id
                            ORDER BY rr.created_at DESC, rr.rowid DESC LIMIT 1) = ?"""
                    )
                    parameters.append(review)
            where = " WHERE " + " AND ".join(conditions) if conditions else ""
            rows = connection.execute(
                """
                SELECT run_id, created_at, incident_id, incident_title, mode, model,
                       fixture_sha256, result_json, metadata_json,
                       (SELECT rr.verdict FROM run_reviews rr
                        WHERE rr.run_id = experiment_runs.run_id
                        ORDER BY rr.created_at DESC, rr.rowid DESC LIMIT 1) AS latest_review
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
        record["latest_review"] = record["reviews"][-1]["verdict"] if record["reviews"] else None
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
            "latest_review": row["latest_review"] if "latest_review" in row.keys() else None,
        }
