from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass
class Snapshot:
    investigations: int
    failures: int
    total_duration_seconds: float
    active: int
    duration_buckets: dict[float, int]


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._investigations = 0
        self._failures = 0
        self._duration = 0.0
        self._active = 0
        self._buckets = {0.1: 0, 0.5: 0, 1.0: 0, 2.5: 0, 5.0: 0, 10.0: 0}

    @contextmanager
    def investigation(self) -> Iterator[None]:
        started = time.perf_counter()
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
                duration = time.perf_counter() - started
                self._duration += duration
                self._active -= 1
                for boundary in self._buckets:
                    if duration <= boundary:
                        self._buckets[boundary] += 1

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(
                self._investigations,
                self._failures,
                self._duration,
                self._active,
                dict(self._buckets),
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
                f'rootsignal_investigation_duration_seconds_bucket{{le="+Inf"}} {snapshot.investigations}',
                f"rootsignal_investigation_duration_seconds_sum {snapshot.total_duration_seconds:.6f}",
                f"rootsignal_investigation_duration_seconds_count {snapshot.investigations}",
                "",
            ]
        )
        return "\n".join(lines)


METRICS = Metrics()
