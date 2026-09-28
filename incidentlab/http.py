from __future__ import annotations

import hashlib
import hmac
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class ApiKeyAuthorizer:
    """Constant-time bearer-key validation with an opt-in local-development default."""

    def __init__(self, configured: str = "") -> None:
        keys = [key.strip() for key in configured.split(",") if key.strip()]
        if any(len(key) < 16 for key in keys):
            raise ValueError("Configured RootSignal API keys must contain at least 16 characters")
        self._digests = tuple(hashlib.sha256(key.encode()).digest() for key in keys)

    @property
    def required(self) -> bool:
        return bool(self._digests)

    def authorize(self, authorization: str | None) -> bool:
        if not self.required:
            return True
        scheme, separator, token = (authorization or "").partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            return False
        presented = hashlib.sha256(token.encode()).digest()
        matched = False
        for expected in self._digests:
            matched = hmac.compare_digest(presented, expected) or matched
        return matched


def request_id(value: str | None) -> str:
    """Return a safe caller-provided correlation ID or generate a new one."""
    if value and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return uuid.uuid4().hex


class RateLimiter:
    """Thread-safe fixed-window limiter suitable for a single API process."""

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("Rate limit and window must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int, int]:
        now = self.clock()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - timestamps[0]) + 0.999))
                return False, 0, retry_after
            timestamps.append(now)
            return True, self.limit - len(timestamps), 0
