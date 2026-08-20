from __future__ import annotations

import argparse
import json
from pathlib import Path

from incidentlab.agent import Investigator
from incidentlab.evaluation import score
from incidentlab.fixtures import load_incident
from evals.statistics import bootstrap_mean_ci


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--minimum", type=float, default=0.80)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--output", type=Path)
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
    confidence_intervals = {
        metric: bootstrap_mean_ci(
            [float(item[metric]) for item in scores],
            samples=args.bootstrap_samples,
            seed=args.seed,
        ).as_dict()
        for metric in metric_names
    }
    report = {
        "schema_version": "3",
        "fixture_count": len(scores),
        "incidents": scores,
        "aggregate": aggregate,
        "confidence_intervals": confidence_intervals,
        "statistics": {
            "method": "nonparametric bootstrap over incidents",
            "seed": args.seed,
            "bootstrap_samples": args.bootstrap_samples,
        },
    }
    payload = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if aggregate["overall"] < args.minimum:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
