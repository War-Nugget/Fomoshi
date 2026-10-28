"""Thin client for Kalshi's public (unauthenticated) market-data API.

Every response is cached briefly so that many Fomoshi users looking at the same
market share one upstream request instead of each hitting Kalshi.
"""

import json
from pathlib import Path
from typing import Any, Protocol

import httpx
from cachetools import TTLCache

from app.config import get_settings

FIXTURES = Path(__file__).parent / "fixtures"

# seconds each kind of response stays cached
TTL = {"events": 30, "markets": 10, "market": 5, "orderbook": 3}


class KalshiError(Exception):
    """Upstream failure or a market that doesn't exist."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class KalshiClient(Protocol):
    async def get_events(
        self, *, cursor: str | None = None, limit: int = 100, series_ticker: str | None = None
    ) -> dict[str, Any]: ...

    async def get_market(self, ticker: str) -> dict[str, Any]: ...

    async def get_markets(self, tickers: list[str]) -> list[dict[str, Any]]: ...

    async def get_event(self, event_ticker: str) -> dict[str, Any]: ...

    async def get_orderbook(self, ticker: str) -> dict[str, Any]: ...


class LiveKalshiClient:
    def __init__(self, base_url: str):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=10.0)
        self._caches = {kind: TTLCache(maxsize=2048, ttl=ttl) for kind, ttl in TTL.items()}

    async def _get(self, kind: str, path: str, params: dict | None = None) -> dict[str, Any]:
        key = (path, tuple(sorted((params or {}).items())))
        cache = self._caches[kind]
        if key in cache:
            return cache[key]
        try:
            resp = await self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise KalshiError(f"Could not reach Kalshi: {exc}") from exc
        if resp.status_code == 404:
            raise KalshiError("Market not found", status_code=404)
        if resp.status_code == 429:
            raise KalshiError("Kalshi rate limit hit, try again shortly", status_code=503)
        if resp.status_code >= 400:
            raise KalshiError(f"Kalshi returned HTTP {resp.status_code}")
        data = resp.json()
        cache[key] = data
        return data

    async def get_events(self, *, cursor=None, limit=100, series_ticker=None):
        params: dict[str, Any] = {"status": "open", "with_nested_markets": "true", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker
        return await self._get("events", "/events", params)

    async def get_market(self, ticker):
        return (await self._get("market", f"/markets/{ticker}"))["market"]

    async def get_markets(self, tickers):
        if not tickers:
            return []
        out: list[dict[str, Any]] = []
        for i in range(0, len(tickers), 100):  # stay well under URL length limits
            chunk = sorted(tickers[i : i + 100])
            data = await self._get(
                "markets", "/markets", {"tickers": ",".join(chunk), "limit": 1000}
            )
            out.extend(data.get("markets", []))
        return out

    async def get_event(self, event_ticker):
        return (await self._get("events", f"/events/{event_ticker}"))["event"]

    async def get_orderbook(self, ticker):
        return await self._get("orderbook", f"/markets/{ticker}/orderbook")

    async def aclose(self):
        await self._http.aclose()


class MockKalshiClient:
    """Serves sample data in Kalshi's real response format. Used for tests, demos, and
    developing offline. Edit app/kalshi/fixtures/*.json to change the data."""

    def __init__(self):
        self.events: list[dict] = json.loads((FIXTURES / "events.json").read_text())["events"]
        self.orderbooks: dict[str, dict] = json.loads((FIXTURES / "orderbooks.json").read_text())

    def _all_markets(self) -> dict[str, dict]:
        return {m["ticker"]: m for e in self.events for m in e.get("markets", [])}

    async def get_events(self, *, cursor=None, limit=100, series_ticker=None):
        events = [
            e for e in self.events if not series_ticker or e["series_ticker"] == series_ticker
        ]
        return {"events": events[:limit], "cursor": ""}

    async def get_market(self, ticker):
        market = self._all_markets().get(ticker)
        if market is None:
            raise KalshiError("Market not found", status_code=404)
        return market

    async def get_markets(self, tickers):
        markets = self._all_markets()
        return [markets[t] for t in tickers if t in markets]

    async def get_event(self, event_ticker):
        for e in self.events:
            if e["event_ticker"] == event_ticker:
                return {k: v for k, v in e.items() if k != "markets"}
        raise KalshiError("Event not found", status_code=404)

    async def get_orderbook(self, ticker):
        await self.get_market(ticker)
        return self.orderbooks.get(ticker, {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}})

    async def aclose(self):
        pass


_client: LiveKalshiClient | MockKalshiClient | None = None


def get_kalshi() -> LiveKalshiClient | MockKalshiClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = (
            MockKalshiClient()
            if settings.kalshi_mode == "mock"
            else LiveKalshiClient(settings.kalshi_base_url)
        )
    return _client
