from __future__ import annotations

import argparse
import json
from pathlib import Path

from incidentlab.agent import Investigator
from incidentlab.evaluation import score
from incidentlab.fixtures import load_incident


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--minimum", type=float, default=0.80)
    args = parser.parse_args()
    paths = sorted([*args.fixtures.glob("*.yaml"), *args.fixtures.glob("*.json")])
    if not paths:
        raise SystemExit("No fixtures found")
    scores = []
    for path in paths:
        incident = load_incident(path)
        scores.append(score(incident, Investigator().investigate(incident)).as_dict())
    metric_names = [
        "root_cause",
        "tool_selection",
        "tool_precision",
        "evidence_coverage",
        "citation_validity",
        "remediation_coverage",
        "overall",
    ]
    aggregate = {
        metric: round(sum(float(item[metric]) for item in scores) / len(scores), 4)
        for metric in metric_names
    }
    report = {"schema_version": "2", "fixture_count": len(scores), "incidents": scores, "aggregate": aggregate}
    print(json.dumps(report, indent=2))
    if aggregate["overall"] < args.minimum:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
