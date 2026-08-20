from __future__ import annotations

import random
import statistics
from dataclasses import dataclass


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("cannot calculate a percentile of an empty sample")
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[max(0, min(index, len(ordered) - 1))]


@dataclass(frozen=True)
class ConfidenceInterval:
    mean: float
    lower: float
    upper: float
    confidence: float
    bootstrap_samples: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "mean": round(self.mean, 6),
            "lower": round(self.lower, 6),
            "upper": round(self.upper, 6),
            "confidence": self.confidence,
            "bootstrap_samples": self.bootstrap_samples,
        }


def bootstrap_mean_ci(
    values: list[float],
    *,
    confidence: float = 0.95,
    samples: int = 10_000,
    seed: int = 17,
) -> ConfidenceInterval:
    if not values:
        raise ValueError("bootstrap requires at least one observation")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between zero and one")
    if samples < 100:
        raise ValueError("bootstrap requires at least 100 samples")
    generator = random.Random(seed)
    means = [
        statistics.mean(generator.choice(values) for _ in values)
        for _ in range(samples)
    ]
    tail = (1 - confidence) / 2
    return ConfidenceInterval(
        statistics.mean(values),
        percentile(means, tail),
        percentile(means, 1 - tail),
        confidence,
        samples,
    )


def paired_comparison(
    baseline: dict[str, float],
    candidate: dict[str, float],
    *,
    confidence: float = 0.95,
    samples: int = 10_000,
    seed: int = 17,
) -> dict[str, object]:
    baseline_ids = set(baseline)
    candidate_ids = set(candidate)
    if baseline_ids != candidate_ids:
        missing = sorted(baseline_ids - candidate_ids)
        extra = sorted(candidate_ids - baseline_ids)
        raise ValueError(f"incident sets differ: missing={missing}, extra={extra}")
    if not baseline_ids:
        raise ValueError("comparison requires at least one paired incident")
    incident_ids = sorted(baseline_ids)
    deltas = [candidate[item] - baseline[item] for item in incident_ids]
    interval = bootstrap_mean_ci(
        deltas, confidence=confidence, samples=samples, seed=seed
    )
    generator = random.Random(seed)
    bootstrap_means = [
        statistics.mean(generator.choice(deltas) for _ in deltas)
        for _ in range(samples)
    ]
    return {
        "paired_incidents": len(incident_ids),
        "incident_deltas": {
            incident_id: round(candidate[incident_id] - baseline[incident_id], 6)
            for incident_id in incident_ids
        },
        "mean_delta": interval.as_dict(),
        "median_delta": round(statistics.median(deltas), 6),
        "wins": sum(delta > 0 for delta in deltas),
        "ties": sum(delta == 0 for delta in deltas),
        "losses": sum(delta < 0 for delta in deltas),
        "probability_of_improvement": round(
            sum(value > 0 for value in bootstrap_means) / samples, 6
        ),
        "seed": seed,
    }
