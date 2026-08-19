from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from incidentlab.evaluation import score
from incidentlab.fixtures import load_incident
from incidentlab.models import Evidence, InvestigationResult, ToolCall


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the live model-backed API")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for path in sorted([*args.fixtures.glob("*.yaml"), *args.fixtures.glob("*.json")]):
        incident = load_incident(path)
        payload = json.dumps({"incident_id": incident.incident_id, "query": incident.summary}).encode()
        request = urllib.request.Request(
            args.url.rstrip("/") + "/v1/investigations",
            data=payload,
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.load(response)
        result = InvestigationResult(
            incident_id=body["incident_id"],
            root_cause=body["root_cause"],
            confidence=body["confidence"],
            evidence=[Evidence(**item) for item in body["evidence"]],
            remediation=body["remediation"],
            tool_calls=[ToolCall(name=item["name"], arguments=item.get("arguments", {})) for item in body["tool_calls"]],
            limitations=body.get("limitations", []),
        )
        rows.append({**score(incident, result).as_dict(), "run": body.get("run", {})})
    metrics = ["root_cause", "tool_selection", "evidence_coverage", "remediation_coverage", "overall"]
    aggregate = {
        metric: round(sum(float(row[metric]) for row in rows) / len(rows), 4) for metric in metrics
    }
    aggregate.update(
        {
            "mean_latency_ms": round(sum(float(row["run"].get("latency_ms", 0)) for row in rows) / len(rows), 2),
            "citation_validity": round(sum(float(row["run"].get("citation_validity", 0)) for row in rows) / len(rows), 4),
            "model_planned_steps": sum(int(row["run"].get("model_planned_steps", 0)) for row in rows),
            "agent_steps": sum(int(row["run"].get("agent_steps", 0)) for row in rows),
        }
    )
    print(json.dumps({"schema_version": "1", "kind": "live-model", "incidents": rows, "aggregate": aggregate}, indent=2))


if __name__ == "__main__":
    main()
