import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self.lock:
            events = self.events[key]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded")
            events.append(now)


suggestion_limiter = SlidingWindowLimiter(limit=20, window_seconds=60)


def limit_suggestion_generation(request: Request) -> None:
    user_key = request.headers.get("Authorization") or (request.client.host if request.client else "unknown")
    suggestion_limiter.check(user_key)
