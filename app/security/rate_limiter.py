import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status

from app.config import settings

class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter per IP/client."""

    def __init__(self, requests_per_minute: int = 120):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int = None, window_seconds: int = None) -> bool:
        max_requests = max_requests or self.requests_per_minute
        window_seconds = window_seconds or self.window_seconds
        now = time.time()
        window_start = now - window_seconds

        # Clean old timestamps
        history = [t for t in self.requests[key] if t > window_start]
        self.requests[key] = history

        if len(history) >= max_requests:
            return False

        self.requests[key].append(now)
        return True

    def reset(self) -> None:
        """Clear all recorded request history (useful for test isolation)."""
        self.requests.clear()

rate_limiter = InMemoryRateLimiter(settings.RATE_LIMIT_REQUESTS_PER_MINUTE)

async def check_rate_limit(request: Request, max_requests: int = None, window: int = 60, key_suffix: str = ""):
    """Dependency or function to verify client rate limit scoped by IP and route."""
    client_ip = request.client.host if request.client else "unknown"
    path = request.scope.get("path", getattr(request.url, "path", "/"))
    key = f"{client_ip}:{path}"
    if key_suffix:
        key += f":{key_suffix}"

    if not rate_limiter.is_allowed(key, max_requests, window):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down your requests.",
        )
