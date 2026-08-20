from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    source: str
    content: str
    relevance: float = 1.0


@dataclass
class Incident:
    incident_id: str
    title: str
    summary: str
    telemetry: dict[str, Any]
    runbooks: list[dict[str, str]]
    oracle: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvestigationResult:
    incident_id: str
    root_cause: str
    confidence: float
    evidence: list[Evidence]
    remediation: list[str]
    tool_calls: list[ToolCall]
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "evidence": [e.__dict__ for e in self.evidence],
            "remediation": self.remediation,
            "tool_calls": [c.__dict__ for c in self.tool_calls],
            "limitations": self.limitations,
        }
