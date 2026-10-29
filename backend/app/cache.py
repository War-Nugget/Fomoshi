"""A tiny async cache with TTLs. Uses Redis when REDIS_URL is set (so every API
instance and the worker share one cache), otherwise an in-process dict."""

import json
import time
from typing import Any, Protocol

from app.config import get_settings


class Cache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: int) -> None: ...
    async def incr(self, key: str, ttl: int) -> int: ...
    async def clear(self) -> None: ...


class MemoryCache:
    def __init__(self, max_items: int = 5000):
        self._data: dict[str, tuple[float, Any]] = {}
        self._max = max_items

    def _prune(self) -> None:
        now = time.monotonic()
        for k in [k for k, (exp, _) in self._data.items() if exp <= now]:
            del self._data[k]
        while len(self._data) > self._max:
            self._data.pop(next(iter(self._data)))

    async def get(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires <= time.monotonic():
            del self._data[key]
            return None
        return value

    async def set(self, key, value, ttl):
        if len(self._data) >= self._max:
            self._prune()
        self._data[key] = (time.monotonic() + ttl, value)

    async def incr(self, key, ttl):
        current = await self.get(key)
        if current is None:
            await self.set(key, 1, ttl)
            return 1
        expires, _ = self._data[key]
        self._data[key] = (expires, current + 1)
        return current + 1

    async def clear(self):
        self._data.clear()


class RedisCache:
    def __init__(self, url: str):
        self._url = url
        self._clients: dict[int, Any] = {}

    @property
    def _redis(self):
        # redis.asyncio connections belong to one event loop, so keep one client per loop.
        import asyncio

        import redis.asyncio as redis

        loop_id = id(asyncio.get_running_loop())
        client = self._clients.get(loop_id)
        if client is None:
            client = self._clients[loop_id] = redis.from_url(self._url, decode_responses=True)
        return client

    async def get(self, key):
        raw = await self._redis.get(f"fomoshi:{key}")
        return json.loads(raw) if raw is not None else None

    async def set(self, key, value, ttl):
        await self._redis.set(f"fomoshi:{key}", json.dumps(value), ex=ttl)

    async def incr(self, key, ttl):
        k = f"fomoshi:{key}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(k)
            pipe.expire(k, ttl, nx=True)
            count, _ = await pipe.execute()
        return int(count)

    async def clear(self):
        keys = [k async for k in self._redis.scan_iter("fomoshi:*")]
        if keys:
            await self._redis.delete(*keys)


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        url = get_settings().redis_url
        _cache = RedisCache(url) if url else MemoryCache()
    return _cache
