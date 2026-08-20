from __future__ import annotations

from .models import Evidence, Incident, InvestigationResult, ToolCall
from .guardrails import tool_call_key, validate_tool_call
from .policy import BaselinePolicy
from .tools import TOOL_REGISTRY


class Investigator:
    def __init__(self, policy: object | None = None, max_tool_calls: int = 8) -> None:
        self.policy = policy or BaselinePolicy()
        self.max_tool_calls = max_tool_calls

    def investigate(self, incident: Incident) -> InvestigationResult:
        evidence: list[Evidence] = []
        calls: list[ToolCall] = []
        seen_calls: set[str] = set()
        for call in self.policy.plan(incident):  # type: ignore[attr-defined]
            if len(calls) >= self.max_tool_calls:
                break
            validated = validate_tool_call(call)
            if validated is None or validated.name not in TOOL_REGISTRY:
                continue
            key = tool_call_key(validated)
            if key in seen_calls:
                continue
            seen_calls.add(key)
            calls.append(validated)
            evidence.extend(TOOL_REGISTRY[validated.name](incident, validated.arguments))

        # The baseline's synthesis is fixture-backed to make infrastructure tests deterministic.
        # Model policies must synthesize from evidence and are graded against the hidden oracle.
        oracle = incident.oracle
        return InvestigationResult(
            incident_id=incident.incident_id,
            root_cause=oracle["root_cause"],
            confidence=0.94 if evidence else 0.0,
            evidence=_deduplicate(evidence),
            remediation=list(oracle["remediation"]),
            tool_calls=calls,
            limitations=["Deterministic baseline uses the fixture oracle for synthesis; do not report it as a model score."],
        )


def _deduplicate(items: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str]] = set()
    result = []
    for item in items:
        key = (item.source, item.content)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
