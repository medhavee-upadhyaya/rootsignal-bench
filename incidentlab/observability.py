from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Mapping

try:
    from opentelemetry import trace
except ImportError:  # pragma: no cover - optional integration
    trace = None


ROUTES = {
    "/healthz",
    "/readyz",
    "/metrics",
    "/v1/system",
    "/v1/benchmarks/latest",
    "/v1/knowledge",
    "/v1/investigations",
    "/v1/baselines/deterministic",
}


@dataclass(frozen=True)
class Snapshot:
    investigations: int
    failures: int
    total_duration_seconds: float
    active: int
    duration_buckets: dict[float, int]
    http_requests: dict[tuple[str, str, str], int]
    http_duration_seconds: dict[tuple[str, str], float]
    model_prompt_tokens: int
    model_completion_tokens: int
    retrieved_chunks: int
    agent_steps: int
    invalid_citations: int
    policy_fallback_steps: int


class Metrics:
    def __init__(self, clock=time.perf_counter) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._investigations = 0
        self._failures = 0
        self._duration = 0.0
        self._active = 0
        self._buckets = {0.1: 0, 0.5: 0, 1.0: 0, 2.5: 0, 5.0: 0, 10.0: 0}
        self._http_requests: Counter[tuple[str, str, str]] = Counter()
        self._http_duration: Counter[tuple[str, str]] = Counter()
        self._model_prompt_tokens = 0
        self._model_completion_tokens = 0
        self._retrieved_chunks = 0
        self._agent_steps = 0
        self._invalid_citations = 0
        self._policy_fallback_steps = 0

    @contextmanager
    def investigation(self) -> Iterator[None]:
        started = self._clock()
        failed = False
        with self._lock:
            self._active += 1
        try:
            yield
        except Exception:
            failed = True
            raise
        finally:
            with self._lock:
                self._investigations += 1
                self._failures += int(failed)
                duration = self._clock() - started
                self._duration += duration
                self._active -= 1
                for boundary in self._buckets:
                    if duration <= boundary:
                        self._buckets[boundary] += 1

    def record_http(self, method: str, path: str, status: int, duration_seconds: float) -> None:
        route = path if path in ROUTES else "other"
        status_class = f"{status // 100}xx"
        with self._lock:
            self._http_requests[(method.upper(), route, status_class)] += 1
            self._http_duration[(method.upper(), route)] += max(duration_seconds, 0.0)

    def record_agent_run(self, run: Mapping[str, object]) -> None:
        steps = int(run.get("agent_steps", 0))
        model_steps = int(run.get("model_planned_steps", 0))
        with self._lock:
            self._model_prompt_tokens += int(run.get("prompt_tokens", 0))
            self._model_completion_tokens += int(run.get("completion_tokens", 0))
            self._retrieved_chunks += int(run.get("retrieved_chunks", 0))
            self._agent_steps += steps
            self._invalid_citations += int(float(run.get("citation_validity", 0)) < 1.0)
            self._policy_fallback_steps += max(steps - model_steps, 0)

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(
                self._investigations,
                self._failures,
                self._duration,
                self._active,
                dict(self._buckets),
                dict(self._http_requests),
                dict(self._http_duration),
                self._model_prompt_tokens,
                self._model_completion_tokens,
                self._retrieved_chunks,
                self._agent_steps,
                self._invalid_citations,
                self._policy_fallback_steps,
            )

    def prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP rootsignal_investigations_total Completed investigations.",
            "# TYPE rootsignal_investigations_total counter",
            f"rootsignal_investigations_total {snapshot.investigations}",
            "# HELP rootsignal_investigation_failures_total Failed investigations.",
            "# TYPE rootsignal_investigation_failures_total counter",
            f"rootsignal_investigation_failures_total {snapshot.failures}",
            "# HELP rootsignal_investigations_active In-flight investigations.",
            "# TYPE rootsignal_investigations_active gauge",
            f"rootsignal_investigations_active {snapshot.active}",
            "# HELP rootsignal_investigation_duration_seconds Investigation latency.",
            "# TYPE rootsignal_investigation_duration_seconds histogram",
        ]
        lines.extend(
            f'rootsignal_investigation_duration_seconds_bucket{{le="{boundary}"}} {count}'
            for boundary, count in snapshot.duration_buckets.items()
        )
        lines.extend(
            [
                f'rootsignal_investigation_duration_seconds_bucket{{le="+Inf"}} '
                f"{snapshot.investigations}",
                f"rootsignal_investigation_duration_seconds_sum "
                f"{snapshot.total_duration_seconds:.6f}",
                f"rootsignal_investigation_duration_seconds_count {snapshot.investigations}",
                "# HELP rootsignal_http_requests_total "
                "HTTP requests by bounded route and status class.",
                "# TYPE rootsignal_http_requests_total counter",
            ]
        )
        lines.extend(
            f'rootsignal_http_requests_total{{method="{method}",route="{route}",'
            f'status_class="{status}"}} {count}'
            for (method, route, status), count in sorted(snapshot.http_requests.items())
        )
        lines.extend(
            [
                "# HELP rootsignal_http_request_duration_seconds_sum Total HTTP request time.",
                "# TYPE rootsignal_http_request_duration_seconds_sum counter",
            ]
        )
        lines.extend(
            f'rootsignal_http_request_duration_seconds_sum{{method="{method}",route="{route}"}} '
            f"{duration:.6f}"
            for (method, route), duration in sorted(snapshot.http_duration_seconds.items())
        )
        counters = {
            "model_prompt_tokens_total": snapshot.model_prompt_tokens,
            "model_completion_tokens_total": snapshot.model_completion_tokens,
            "retrieved_chunks_total": snapshot.retrieved_chunks,
            "agent_steps_total": snapshot.agent_steps,
            "invalid_citations_total": snapshot.invalid_citations,
            "policy_fallback_steps_total": snapshot.policy_fallback_steps,
        }
        for name, value in counters.items():
            lines.extend([f"# TYPE rootsignal_{name} counter", f"rootsignal_{name} {value}"])
        return "\n".join([*lines, ""])


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    safe_fields = {key: value for key, value in fields.items() if value is not None}
    logger.info(json.dumps({"event": event, **safe_fields}, sort_keys=True, default=str))


@contextmanager
def trace_span(name: str, attributes: Mapping[str, object] | None = None) -> Iterator[None]:
    if trace is None:
        yield
        return
    tracer = trace.get_tracer("rootsignal")
    with tracer.start_as_current_span(name, attributes=dict(attributes or {})):
        yield


METRICS = Metrics()
