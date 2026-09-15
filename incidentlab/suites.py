from __future__ import annotations

from typing import Any

from evals.statistics import bootstrap_mean_ci

from .evaluation import score
from .models import Evidence, Incident, InvestigationResult, ToolCall

METRICS = (
    "root_cause", "tool_selection", "tool_precision", "evidence_coverage",
    "citation_validity", "remediation_coverage", "overall",
)


def _result(payload: dict[str, Any]) -> InvestigationResult:
    return InvestigationResult(
        incident_id=str(payload["incident_id"]),
        root_cause=str(payload["root_cause"]),
        confidence=float(payload.get("confidence", 0)),
        evidence=[Evidence(**item) for item in payload.get("evidence", [])],
        remediation=[str(item) for item in payload.get("remediation", [])],
        tool_calls=[ToolCall.from_record(item) for item in payload.get("tool_calls", [])],
        limitations=[str(item) for item in payload.get("limitations", [])],
    )


def build_suite(entries: list[tuple[Incident, dict[str, Any]]]) -> dict[str, Any]:
    if len(entries) < 2:
        raise ValueError("Evaluation suite requires at least two model runs")
    incident_ids = [incident.incident_id for incident, _ in entries]
    if len(set(incident_ids)) != len(incident_ids):
        raise ValueError("Evaluation suite requires one run per incident")
    if any(run.get("mode") != "model" for _, run in entries):
        raise ValueError("Evaluation suite accepts model-backed runs only")

    rows = []
    for incident, run in sorted(entries, key=lambda item: item[0].incident_id):
        scorecard = score(incident, _result(run["result"])).as_dict()
        rows.append({"run_id": run["run_id"], "model": run["model"], **scorecard})
    aggregate = {
        metric: round(sum(float(row[metric]) for row in rows) / len(rows), 4)
        for metric in METRICS
    }
    intervals = {
        metric: bootstrap_mean_ci(
            [float(row[metric]) for row in rows], samples=2_000, seed=17
        ).as_dict()
        for metric in METRICS
    }
    return {
        "schema_version": "1",
        "kind": "saved-model-run-suite",
        "fixture_count": len(rows),
        "models": sorted({str(row["model"]) for row in rows}),
        "incidents": rows,
        "aggregate": aggregate,
        "confidence_intervals": intervals,
        "statistics": {"method": "nonparametric bootstrap over incidents", "seed": 17, "bootstrap_samples": 2_000},
    }
