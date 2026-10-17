"""Request rate limiting and CPU concurrency limits for recognition."""
import os
import threading
import time
from collections import defaultdict, deque

from app.config import RATE_LIMIT_PER_MINUTE, RECOGNITION_CONCURRENCY


class RateLimiter:
    """
    Sliding-window limiter keyed by client (e.g. IP address).
    State is per process: with N server workers, a client can make up to N times the limit.
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.max_requests <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            # Forget idle clients so the table doesn't grow without bound
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]
            return True


recognition_limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)

# Fingerprinting is CPU-bound; queue extra requests instead of oversubscribing the CPU
recognition_slots = threading.BoundedSemaphore(RECOGNITION_CONCURRENCY or os.cpu_count() or 1)
