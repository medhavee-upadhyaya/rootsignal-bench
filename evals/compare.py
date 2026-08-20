from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.statistics import paired_comparison


def load_metric(path: Path, metric: str) -> tuple[dict[str, float], dict[str, object]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema_version") != "3":
        raise ValueError(f"{path} is not an evaluation schema v3 report")
    incidents = report.get("incidents")
    if not isinstance(incidents, list):
        raise ValueError(f"{path} has no incident scorecards")
    values = {str(item["incident_id"]): float(item[metric]) for item in incidents}
    return values, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Paired statistical comparison of evaluation reports")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--metric", default="overall")
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-regression", type=float, default=0.0)
    parser.add_argument("--minimum-lower-bound", type=float)
    parser.add_argument("--minimum-probability", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        baseline, baseline_report = load_metric(args.baseline, args.metric)
        candidate, candidate_report = load_metric(args.candidate, args.metric)
        comparison = paired_comparison(
            baseline,
            candidate,
            confidence=args.confidence,
            samples=args.bootstrap_samples,
            seed=args.seed,
        )
    except (KeyError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    mean_delta = comparison["mean_delta"]
    assert isinstance(mean_delta, dict)
    checks = {
        "mean_within_tolerance": float(mean_delta["mean"]) >= -args.max_regression,
        "lower_bound": (
            args.minimum_lower_bound is None
            or float(mean_delta["lower"]) >= args.minimum_lower_bound
        ),
        "probability_of_improvement": (
            float(comparison["probability_of_improvement"]) >= args.minimum_probability
        ),
    }
    passed = all(checks.values())
    result = {
        "schema_version": "1",
        "kind": "paired-evaluation-comparison",
        "metric": args.metric,
        "baseline_fixture_count": baseline_report["fixture_count"],
        "candidate_fixture_count": candidate_report["fixture_count"],
        "comparison": comparison,
        "gate": {
            "max_regression": args.max_regression,
            "minimum_lower_bound": args.minimum_lower_bound,
            "minimum_probability": args.minimum_probability,
            "checks": checks,
            "passed": passed,
        },
    }
    payload = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
