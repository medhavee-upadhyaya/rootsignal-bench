from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def request_once(url: str, incident_id: str) -> tuple[float, bool]:
    body = json.dumps({"incident_id": incident_id}).encode()
    request = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
            return time.perf_counter() - started, response.status < 400
    except Exception:
        return time.perf_counter() - started, False


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(round((len(values) - 1) * fraction), len(values) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--incident-id", default="checkout-latency-001")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--slo-p95-ms", type=float, default=5000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    for _ in range(args.warmup):
        request_once(args.url, args.incident_id)
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda _: request_once(args.url, args.incident_id), range(args.requests)))
    duration = time.perf_counter() - started
    latencies = [latency for latency, _ in results]
    report = {
        "schema_version": "2",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.url,
        "incident_id": args.incident_id,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "success_rate": sum(ok for _, ok in results) / len(results),
        "throughput_rps": round(args.requests / duration, 3),
        "latency_ms": {
            "mean": round(statistics.mean(latencies) * 1000, 3),
            "p50": round(percentile(latencies, 0.50) * 1000, 3),
            "p95": round(percentile(latencies, 0.95) * 1000, 3),
            "p99": round(percentile(latencies, 0.99) * 1000, 3),
        },
    }
    report["slo"] = {
        "p95_target_ms": args.slo_p95_ms,
        "passed": report["success_rate"] == 1.0 and report["latency_ms"]["p95"] <= args.slo_p95_ms,
    }
    payload = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
