"""Per-visitor and per-IP rate limits for POST /api/chat (sliding one-hour window, in memory).

In memory means per server process: with several Uvicorn workers or servers, each keeps its own
counts. That is fine for one small server; move it to Redis if Coltek ever runs more than one.
"""
import threading
import time
from collections import defaultdict, deque

WINDOW_SECONDS = 3600
IP_MULTIPLIER = 5   # many visitors can share one IP (mobile networks in Ghana use carrier NAT)


class RateLimiter:
    def __init__(self, per_hour: int):
        self.per_hour = per_hour
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _check(self, key: str, limit: int, now: float) -> int:
        """0 if allowed (and counted), else the seconds until the next request is allowed."""
        hits = self._hits[key]
        while hits and hits[0] <= now - WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= limit:
            return int(hits[0] + WINDOW_SECONDS - now) + 1
        return 0

    def hit(self, visitor_id: str, ip: str | None) -> int:
        """Count one chat message. Returns 0 if allowed, else seconds to wait (nothing is counted then)."""
        now = time.monotonic()
        checks = [(f"visitor:{visitor_id}", self.per_hour)]
        if ip:
            checks.append((f"ip:{ip}", self.per_hour * IP_MULTIPLIER))
        with self._lock:
            for key, limit in checks:
                wait = self._check(key, limit, now)
                if wait:
                    return wait
            for key, _ in checks:
                self._hits[key].append(now)
        return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
