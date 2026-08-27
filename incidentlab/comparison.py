from __future__ import annotations

from typing import Any, Literal

from .evaluation import score
from .models import Evidence, Incident, InvestigationResult, ToolCall

Verdict = Literal["improved", "regressed", "unchanged"]
QUALITY_METRICS = (
    "root_cause",
    "tool_selection",
    "tool_precision",
    "evidence_coverage",
    "citation_validity",
    "remediation_coverage",
    "overall",
)


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


def compare_runs(
    incident: Incident, reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    if reference["incident_id"] != candidate["incident_id"]:
        raise ValueError("Runs must use the same incident")
    if reference["fixture_sha256"] != candidate["fixture_sha256"]:
        raise ValueError("Runs must use the same incident fixture revision")

    reference_score = score(incident, _result(reference["result"])).as_dict()
    candidate_score = score(incident, _result(candidate["result"])).as_dict()
    deltas = {
        metric: round(float(candidate_score[metric]) - float(reference_score[metric]), 4)
        for metric in QUALITY_METRICS
    }
    reference_latency = float(reference["metadata"].get("latency_ms", 0))
    candidate_latency = float(candidate["metadata"].get("latency_ms", 0))
    latency_delta = round(candidate_latency - reference_latency, 3)
    latency_percent = (
        round((latency_delta / reference_latency) * 100, 2) if reference_latency > 0 else None
    )

    material_quality_loss = any(
        deltas[metric] < -0.1
        for metric in ("root_cause", "tool_selection", "evidence_coverage", "citation_validity")
    )
    material_quality_gain = deltas["overall"] > 0.02
    latency_regression = bool(
        latency_percent is not None and latency_percent > 20 and latency_delta > 100
    )
    latency_improvement = bool(
        latency_percent is not None and latency_percent < -20 and latency_delta < -100
    )

    reasons: list[str] = []
    if deltas["overall"] < -0.02 or material_quality_loss:
        verdict: Verdict = "regressed"
        reasons.append(f"Overall quality changed by {deltas['overall']:+.3f}.")
        for metric in ("root_cause", "tool_selection", "evidence_coverage", "citation_validity"):
            if deltas[metric] < -0.1:
                label = metric.replace("_", " ").title()
                reasons.append(f"{label} fell by {abs(deltas[metric]):.3f}.")
    elif latency_regression and not material_quality_gain:
        verdict = "regressed"
        reasons.append(
            f"Latency increased by {latency_percent:.1f}% without a material quality gain."
        )
    elif material_quality_gain:
        verdict = "improved"
        reasons.append(f"Overall quality improved by {deltas['overall']:+.3f}.")
    elif latency_improvement and deltas["overall"] >= -0.02:
        verdict = "improved"
        reasons.append(f"Latency decreased by {abs(latency_percent):.1f}% with stable quality.")
    else:
        verdict = "unchanged"
        reasons.append("No quality or latency change crossed the materiality thresholds.")

    return {
        "schema_version": "1.0",
        "incident_id": incident.incident_id,
        "fixture_sha256": reference["fixture_sha256"],
        "verdict": verdict,
        "reasons": reasons,
        "thresholds": {"overall": 0.02, "dimension": 0.1, "latency_percent": 20, "latency_ms": 100},
        "reference": {"run": _run_identity(reference), "scorecard": reference_score},
        "candidate": {"run": _run_identity(candidate), "scorecard": candidate_score},
        "deltas": {**deltas, "latency_ms": latency_delta, "latency_percent": latency_percent},
    }


def _run_identity(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "created_at": run["created_at"],
        "mode": run["mode"],
        "model": run["model"],
        "latency_ms": run["metadata"].get("latency_ms", 0),
        "root_cause": run["result"].get("root_cause", ""),
    }
