from __future__ import annotations

import argparse
import concurrent.futures
import json
import platform
import statistics
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from benchmarks.load_test import percentile


@dataclass(frozen=True)
class Sample:
    latency_ms: float
    ttft_ms: float | None
    output_tokens: int
    ok: bool
    error: str | None = None


def parse_sse(
    lines: Iterable[bytes],
    started: float,
    clock: Callable[[], float] = time.perf_counter,
) -> Sample:
    first_token_at: float | None = None
    output_tokens = 0
    error: str | None = None
    try:
        for raw_line in lines:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            payload = json.loads(data)
            if payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            choices = payload.get("choices", [])
            content = choices[0].get("delta", {}).get("content") if choices else None
            if content:
                if first_token_at is None:
                    first_token_at = clock()
                output_tokens += 1
            usage = payload.get("usage") or {}
            if usage.get("completion_tokens") is not None:
                output_tokens = int(usage["completion_tokens"])
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    ended = clock()
    return Sample(
        latency_ms=(ended - started) * 1000,
        ttft_ms=None if first_token_at is None else (first_token_at - started) * 1000,
        output_tokens=output_tokens,
        ok=error is None and first_token_at is not None,
        error=error or (None if first_token_at is not None else "stream returned no output token"),
    )


def request_once(
    url: str, model: str, prompt: str, max_tokens: int, timeout: float = 120
) -> Sample:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
    ).encode()
    request = urllib.request.Request(
        url, data=body, headers={"content-type": "application/json", "accept": "text/event-stream"}
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return parse_sse(response, started)
    except Exception as exc:
        return Sample(
            (time.perf_counter() - started) * 1000,
            None,
            0,
            False,
            f"{type(exc).__name__}: {exc}",
        )


def build_report(
    samples: list[Sample], duration_s: float, concurrency: int, metadata: dict[str, object]
) -> dict[str, object]:
    successful = [sample for sample in samples if sample.ok]
    latencies = [sample.latency_ms for sample in successful]
    ttfts = [sample.ttft_ms for sample in successful if sample.ttft_ms is not None]
    output_tokens = sum(sample.output_tokens for sample in successful)

    def summary(values: list[float]) -> dict[str, float]:
        if not values:
            return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        return {
            "mean": round(statistics.mean(values), 3),
            "p50": round(percentile(values, 0.50), 3),
            "p95": round(percentile(values, 0.95), 3),
            "p99": round(percentile(values, 0.99), 3),
        }

    return {
        "schema_version": "1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "runtime": metadata,
        "concurrency": concurrency,
        "requests": len(samples),
        "successful_requests": len(successful),
        "success_rate": round(len(successful) / len(samples), 4) if samples else 0.0,
        "request_throughput_rps": round(len(successful) / duration_s, 3) if duration_s else 0.0,
        "output_throughput_tokens_per_second": (
            round(output_tokens / duration_s, 3) if duration_s else 0.0
        ),
        "output_tokens": output_tokens,
        "latency_ms": summary(latencies),
        "ttft_ms": summary(ttfts),
        "errors": [asdict(sample) for sample in samples if not sample.ok],
    }


def evaluate_slo(
    report: dict[str, object],
    max_p95_ms: float,
    max_ttft_p95_ms: float,
    minimum_success_rate: float,
) -> dict[str, object]:
    latency = report["latency_ms"]
    ttft = report["ttft_ms"]
    assert isinstance(latency, dict) and isinstance(ttft, dict)
    checks = {
        "latency_p95": float(latency["p95"]) <= max_p95_ms,
        "ttft_p95": float(ttft["p95"]) <= max_ttft_p95_ms,
        "success_rate": float(report["success_rate"]) >= minimum_success_rate,
    }
    return {
        "targets": {
            "max_latency_p95_ms": max_p95_ms,
            "max_ttft_p95_ms": max_ttft_p95_ms,
            "minimum_success_rate": minimum_success_rate,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def run_point(args: argparse.Namespace, concurrency: int) -> dict[str, object]:
    for _ in range(args.warmup):
        request_once(args.url, args.model, args.prompt, args.max_tokens, args.timeout)
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        samples = list(
            pool.map(
                lambda _: request_once(
                    args.url, args.model, args.prompt, args.max_tokens, args.timeout
                ),
                range(args.requests),
            )
        )
    duration = time.perf_counter() - started
    metadata = {
        "server": args.server,
        "url": args.url,
        "model": args.model,
        "model_revision": args.model_revision,
        "dtype": args.dtype,
        "quantization": args.quantization,
        "tensor_parallel_size": args.tensor_parallel_size,
        "hardware": args.hardware,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "max_tokens": args.max_tokens,
        "prompt": args.prompt,
    }
    report = build_report(samples, duration, concurrency, metadata)
    report["slo"] = evaluate_slo(
        report, args.max_p95_ms, args.max_ttft_p95_ms, args.minimum_success_rate
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark an OpenAI-compatible streaming inference server"
    )
    parser.add_argument("--url", default="http://127.0.0.1:8001/v1/chat/completions")
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--hardware", required=True)
    parser.add_argument("--server", default="vllm")
    parser.add_argument("--dtype", default="auto")
    parser.add_argument("--quantization", default="none")
    parser.add_argument("--tensor-parallel-size", type=int, default=1)
    parser.add_argument(
        "--prompt", default="Summarize the likely cause of a database latency incident."
    )
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency-sweep", default="1,2,4,8")
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-p95-ms", type=float, default=10000)
    parser.add_argument("--max-ttft-p95-ms", type=float, default=2000)
    parser.add_argument("--minimum-success-rate", type=float, default=0.99)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sweep = [int(value) for value in args.concurrency_sweep.split(",") if value.strip()]
    if not sweep or min(sweep) < 1 or args.requests < 1:
        parser.error("requests and concurrency values must be positive")
    reports = [run_point(args, concurrency) for concurrency in sweep]
    payload = {
        "benchmark": "openai-compatible-streaming-inference",
        "schema_version": "1",
        "sweep": reports,
        "passed": all(bool(report["slo"]["passed"]) for report in reports),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    raise SystemExit(0 if payload["passed"] else 1)


if __name__ == "__main__":
    main()
