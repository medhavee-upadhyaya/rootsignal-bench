from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare_points(baseline: dict, candidate: dict) -> dict[str, float]:
    def change(new: float, old: float) -> float:
        return round(((new - old) / old) * 100, 3) if old else 0.0

    return {
        "latency_p95_change_percent": change(
            candidate["latency_ms"]["p95"], baseline["latency_ms"]["p95"]
        ),
        "ttft_p95_change_percent": change(candidate["ttft_ms"]["p95"], baseline["ttft_ms"]["p95"]),
        "token_throughput_change_percent": change(
            candidate["output_throughput_tokens_per_second"],
            baseline["output_throughput_tokens_per_second"],
        ),
        "success_rate_change": round(candidate["success_rate"] - baseline["success_rate"], 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare matching inference benchmark sweeps")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    baseline_points = {point["concurrency"]: point for point in baseline["sweep"]}
    candidate_points = {point["concurrency"]: point for point in candidate["sweep"]}
    shared = sorted(baseline_points.keys() & candidate_points.keys())
    if not shared:
        parser.error("benchmark files have no matching concurrency points")
    result = {
        str(value): compare_points(baseline_points[value], candidate_points[value])
        for value in shared
    }
    print(json.dumps({"comparison": result}, indent=2))


if __name__ == "__main__":
    main()
