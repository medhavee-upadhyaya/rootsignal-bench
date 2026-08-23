from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from incidentlab.fixtures import load_incident


KNOWN_TOOLS = {
    "query_logs",
    "query_metrics",
    "query_deployments",
    "retrieve_knowledge",
    "search_runbooks",
}


def _evidence_is_grounded(evidence: str, public_observations: str) -> bool:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9_.%-]+", evidence.lower())
        if len(token) >= 3
    ]
    return bool(tokens) and any(token in public_observations for token in tokens)


def audit(paths: list[Path]) -> dict[str, object]:
    incidents = [load_incident(path) for path in paths]
    ids = [incident.incident_id for incident in incidents]
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    public_hashes: dict[str, list[str]] = {}
    oracle_leaks: list[str] = []
    ungrounded_evidence: dict[str, list[str]] = {}
    unknown_expected_tools: dict[str, list[str]] = {}
    for incident in incidents:
        public = {
            "title": incident.title,
            "summary": incident.summary,
            "telemetry": incident.telemetry,
            "runbooks": incident.runbooks,
        }
        serialized = json.dumps(public, sort_keys=True).lower()
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        public_hashes.setdefault(digest, []).append(incident.incident_id)
        if incident.oracle["root_cause"].strip().lower() in serialized:
            oracle_leaks.append(incident.incident_id)
        public_observations = json.dumps(
            {"telemetry": incident.telemetry, "runbooks": incident.runbooks}, sort_keys=True
        ).lower()
        missing = [
            item
            for item in incident.oracle["required_evidence"]
            if not _evidence_is_grounded(item, public_observations)
        ]
        if missing:
            ungrounded_evidence[incident.incident_id] = missing
        unknown = sorted(set(incident.oracle["expected_tools"]) - KNOWN_TOOLS)
        if unknown:
            unknown_expected_tools[incident.incident_id] = unknown
    duplicate_observations = [sorted(values) for values in public_hashes.values() if len(values) > 1]
    failure_classes = Counter(str(item.metadata["failure_class"]) for item in incidents)
    difficulties = Counter(str(item.metadata["difficulty"]) for item in incidents)
    licenses = Counter(str(item.metadata["license"]) for item in incidents)
    checks = {
        "fixtures_present": bool(incidents),
        "unique_incident_ids": not duplicate_ids,
        "unique_public_observations": not duplicate_observations,
        "no_exact_oracle_leakage": not oracle_leaks,
        "required_evidence_grounded": not ungrounded_evidence,
        "expected_tools_recognized": not unknown_expected_tools,
        "all_synthetic": all(item.metadata["synthetic"] is True for item in incidents),
        "failure_classes_declared": len(failure_classes) > 0,
        "difficulty_levels_covered": set(difficulties) == {"easy", "medium", "hard"},
        "difficulty_declared": len(difficulties) > 0,
        "licenses_declared": len(licenses) > 0,
    }
    return {
        "schema_version": "1",
        "fixture_count": len(incidents),
        "checks": checks,
        "passed": all(checks.values()),
        "failure_classes": dict(sorted(failure_classes.items())),
        "difficulties": dict(sorted(difficulties.items())),
        "licenses": dict(sorted(licenses.items())),
        "duplicate_ids": duplicate_ids,
        "duplicate_public_observations": duplicate_observations,
        "exact_oracle_leaks": oracle_leaks,
        "ungrounded_evidence": ungrounded_evidence,
        "unknown_expected_tools": unknown_expected_tools,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit benchmark fixture integrity")
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = sorted([*args.fixtures.glob("*.yaml"), *args.fixtures.glob("*.json")])
    report = audit(paths)
    payload = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
