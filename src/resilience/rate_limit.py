"""Legacy rate_limit behavior extracted without changing data policies."""

import threading
import time

class RateLimiter:
    """
    Thread-safe minimum-interval rate limiter. Used so that concurrent
    fetch workers still collectively respect a global pace, instead of
    each thread's own time.sleep() only limiting itself while every
    thread fires at once.
    """
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()
