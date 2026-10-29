"""Fixed-window rate limiting keyed by client IP, shared through the cache."""

import time

from fastapi import HTTPException, Request, status

from app.cache import get_cache
from app.config import get_settings


def _now() -> float:  # separate so tests can pin the clock
    return time.time()


def client_ip(request: Request) -> str:
    # Behind a proxy, uvicorn's --proxy-headers sets request.client from X-Forwarded-For.
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window_seconds: int):
    """FastAPI dependency: allow `limit` requests per `window_seconds` per IP."""

    async def dependency(request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        window = int(_now() // window_seconds)
        key = f"rl:{name}:{client_ip(request)}:{window}"
        count = await get_cache().incr(key, window_seconds)
        if count > limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many attempts. Wait a minute and try again.",
                headers={"Retry-After": str(window_seconds)},
            )

    return dependency
