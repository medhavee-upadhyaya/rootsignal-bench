from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .models import Incident, InvestigationResult


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_.-]+", text.lower()))


def _coverage(expected: list[str], actual: list[str]) -> float:
    if not expected:
        return 1.0
    actual_terms = _terms(" ".join(actual))
    matched = sum(bool(_terms(item) & actual_terms) for item in expected)
    return matched / len(expected)


@dataclass(frozen=True)
class Scorecard:
    incident_id: str
    root_cause: float
    tool_selection: float
    evidence_coverage: float
    remediation_coverage: float
    tool_precision: float
    citation_validity: float
    overall: float

    def as_dict(self) -> dict[str, str | float]:
        return asdict(self)


def score(incident: Incident, result: InvestigationResult) -> Scorecard:
    oracle = incident.oracle
    root_terms = _terms(oracle["root_cause"])
    predicted_terms = _terms(result.root_cause)
    root_score = len(root_terms & predicted_terms) / max(len(root_terms), 1)

    expected_tools = set(oracle["expected_tools"])
    actual_tools = {call.name for call in result.tool_calls}
    tool_score = len(expected_tools & actual_tools) / max(len(expected_tools), 1)
    tool_precision = len(expected_tools & actual_tools) / max(len(actual_tools), 1)

    evidence_score = _coverage(
        oracle["required_evidence"], [evidence.content for evidence in result.evidence]
    )
    remediation_score = _coverage(oracle["remediation"], result.remediation)
    citation_validity = sum(bool(item.source and item.content.strip()) for item in result.evidence) / max(
        len(result.evidence), 1
    )
    overall = (
        0.30 * root_score
        + 0.15 * tool_score
        + 0.10 * tool_precision
        + 0.20 * evidence_score
        + 0.10 * citation_validity
        + 0.15 * remediation_score
    )
    return Scorecard(
        incident_id=incident.incident_id,
        root_cause=round(root_score, 4),
        tool_selection=round(tool_score, 4),
        evidence_coverage=round(evidence_score, 4),
        remediation_coverage=round(remediation_score, 4),
        tool_precision=round(tool_precision, 4),
        citation_validity=round(citation_validity, 4),
        overall=round(overall, 4),
    )
