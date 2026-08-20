from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from incidentlab.fixtures import load_incident


def audit(paths: list[Path]) -> dict[str, object]:
    incidents = [load_incident(path) for path in paths]
    ids = [incident.incident_id for incident in incidents]
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    public_hashes: dict[str, list[str]] = {}
    oracle_leaks: list[str] = []
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
    duplicate_observations = [sorted(values) for values in public_hashes.values() if len(values) > 1]
    failure_classes = Counter(str(item.metadata["failure_class"]) for item in incidents)
    difficulties = Counter(str(item.metadata["difficulty"]) for item in incidents)
    licenses = Counter(str(item.metadata["license"]) for item in incidents)
    checks = {
        "fixtures_present": bool(incidents),
        "unique_incident_ids": not duplicate_ids,
        "unique_public_observations": not duplicate_observations,
        "no_exact_oracle_leakage": not oracle_leaks,
        "all_synthetic": all(item.metadata["synthetic"] is True for item in incidents),
        "failure_classes_declared": len(failure_classes) > 0,
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
