"""Thin client for Kalshi's public (unauthenticated) market-data API.

Responses are cached (in Redis when configured) so that many Fomoshi users looking
at the same market share one upstream request instead of each hitting Kalshi.
"""

import asyncio
import hashlib
import json
import math
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.cache import get_cache
from app.config import get_settings

FIXTURES = Path(__file__).parent / "fixtures"

# seconds each kind of response stays cached
TTL = {
    "events": 30,
    "event": 15,
    "markets": 10,
    "live": 2,  # game prices, which move fast while a game is on
    "market": 5,
    "orderbook": 3,
    "candles": 60,
}


class KalshiError(Exception):
    """Upstream failure or a market that doesn't exist."""

    def __init__(self, message: str, status_code: int = 502, *, rate_limited: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limited = rate_limited


class KalshiClient(Protocol):
    async def get_events(
        self, *, cursor: str | None = None, limit: int = 100, series_ticker: str | None = None
    ) -> dict[str, Any]: ...

    async def get_all_open_events(
        self, max_pages: int = 50, series_ticker: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def get_milestones(
        self, min_start: datetime, max_pages: int = 30
    ) -> list[dict[str, Any]]:
        """Kalshi's sports schedule: one milestone per game, with its start time and the
        event tickers it belongs to."""
        ...

    async def get_event(self, event_ticker: str) -> dict[str, Any]:
        """Returns {"event": {...}, "markets": [...]}."""
        ...

    async def get_market(self, ticker: str, *, fresh: bool = False) -> dict[str, Any]:
        """`fresh` skips the cache read (the response still refreshes the cache)."""
        ...

    async def get_markets(self, tickers: list[str], *, live: bool = False) -> list[dict[str, Any]]:
        """`live` caches for a couple of seconds instead of the usual markets TTL."""
        ...

    async def get_orderbook(self, ticker: str, *, fresh: bool = False) -> dict[str, Any]: ...

    async def get_market_candlesticks(
        self, series_ticker: str, ticker: str, start_ts: int, end_ts: int, interval: int
    ) -> list[dict[str, Any]]: ...

    async def get_event_candlesticks(
        self, series_ticker: str, event_ticker: str, start_ts: int, end_ts: int, interval: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Returns {market_ticker: [candles...]}."""
        ...

    async def aclose(self) -> None: ...


class LiveKalshiClient:
    def __init__(self, base_url: str):
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=15.0, headers={"User-Agent": "Fomoshi/1.0"}
        )

    async def _get(
        self,
        kind: str,
        path: str,
        params: dict | None = None,
        *,
        cache: bool = True,
        fresh: bool = False,
    ) -> dict[str, Any]:
        key = f"kalshi:{path}?{json.dumps(params or {}, sort_keys=True)}"
        if cache and not fresh and (hit := await get_cache().get(key)) is not None:
            return hit
        try:
            resp = await self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise KalshiError(f"Could not reach Kalshi: {exc}") from exc
        if resp.status_code == 404:
            raise KalshiError("Market not found", status_code=404)
        if resp.status_code == 429:
            raise KalshiError(
                "Kalshi rate limit hit, try again shortly", status_code=503, rate_limited=True
            )
        if resp.status_code >= 400:
            raise KalshiError(f"Kalshi returned HTTP {resp.status_code}")
        data = resp.json()
        if cache:
            await get_cache().set(key, data, TTL[kind])
        return data

    async def get_events(self, *, cursor=None, limit=100, series_ticker=None):
        params: dict[str, Any] = {"status": "open", "with_nested_markets": "true", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker
        return await self._get("events", "/events", params)

    async def _all_pages(self, path: str, key: str, params: dict, max_pages: int) -> list[dict]:
        """Every page of a cursor-paginated listing, for the background worker. A rate
        limit waits and retries rather than failing a sync that's already made many
        requests."""
        items: list[dict] = []
        cursor = None
        for _ in range(max_pages):
            page_params = {**params, "limit": 200, **({"cursor": cursor} if cursor else {})}
            for wait in (1, 2, 4, 8, None):
                try:
                    page = await self._get("events", path, page_params, cache=False)
                    break
                except KalshiError as exc:
                    if not exc.rate_limited or wait is None:
                        raise
                    await asyncio.sleep(wait)
            items.extend(page.get(key) or [])
            cursor = page.get("cursor")
            if not cursor:
                break
            await asyncio.sleep(0.2)  # stay polite with Kalshi's rate limits
        return items

    async def get_all_open_events(self, max_pages=50, series_ticker=None):
        params = {"status": "open", "with_nested_markets": "true"}
        if series_ticker:
            params["series_ticker"] = series_ticker
        return await self._all_pages("/events", "events", params, max_pages)

    async def get_milestones(self, min_start, max_pages=30):
        # The API ignores an upper bound on start date and doesn't sort by it, so read
        # every page from `min_start` on and let the caller filter.
        params = {
            "category": "Sports",
            "minimum_start_date": min_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        return await self._all_pages("/milestones", "milestones", params, max_pages)

    async def get_event(self, event_ticker):
        data = await self._get("event", f"/events/{event_ticker}")
        event = data["event"]
        markets = data.get("markets") or event.get("markets") or []
        return {"event": {k: v for k, v in event.items() if k != "markets"}, "markets": markets}

    async def get_market(self, ticker, *, fresh=False):
        return (await self._get("market", f"/markets/{ticker}", fresh=fresh))["market"]

    async def get_markets(self, tickers, *, live=False):
        if not tickers:
            return []
        out: list[dict[str, Any]] = []
        for i in range(0, len(tickers), 100):  # stay well under URL length limits
            chunk = sorted(tickers[i : i + 100])
            data = await self._get(
                "live" if live else "markets",
                "/markets",
                {"tickers": ",".join(chunk), "limit": 1000},
            )
            out.extend(data.get("markets", []))
        return out

    async def get_orderbook(self, ticker, *, fresh=False):
        return await self._get("orderbook", f"/markets/{ticker}/orderbook", fresh=fresh)

    async def get_market_candlesticks(self, series_ticker, ticker, start_ts, end_ts, interval):
        data = await self._get(
            "candles",
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            {"start_ts": start_ts, "end_ts": end_ts, "period_interval": interval},
        )
        return data.get("candlesticks") or []

    async def get_event_candlesticks(self, series_ticker, event_ticker, start_ts, end_ts, interval):
        data = await self._get(
            "candles",
            f"/series/{series_ticker}/events/{event_ticker}/candlesticks",
            {"start_ts": start_ts, "end_ts": end_ts, "period_interval": interval},
        )
        tickers = data.get("market_tickers") or []
        candles = data.get("market_candlesticks") or []
        return {t: c or [] for t, c in zip(tickers, candles, strict=False)}

    async def aclose(self):
        await self._http.aclose()


class MockKalshiClient:
    """Serves sample data in Kalshi's real response format. Used for tests, demos, and
    developing offline. Edit app/kalshi/fixtures/*.json to change the data."""

    # Milestone start times in the fixtures count from this moment, which is moved to
    # "now" on load so the sample games are always live or coming up.
    FIXTURE_NOW = datetime(2030, 1, 1, tzinfo=UTC)

    def __init__(self):
        self.events: list[dict] = json.loads((FIXTURES / "events.json").read_text())["events"]
        self.orderbooks: dict[str, dict] = json.loads((FIXTURES / "orderbooks.json").read_text())
        self.milestones: list[dict] = json.loads((FIXTURES / "milestones.json").read_text())[
            "milestones"
        ]
        shift = datetime.now(UTC) - self.FIXTURE_NOW
        for m in self.milestones:
            m["start_date"] = (_parse(m["start_date"]) + shift).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _all_markets(self) -> dict[str, dict]:
        return {m["ticker"]: m for e in self.events for m in e.get("markets", [])}

    async def get_events(self, *, cursor=None, limit=100, series_ticker=None):
        events = [
            e for e in self.events if not series_ticker or e["series_ticker"] == series_ticker
        ]
        return {"events": events[:limit], "cursor": ""}

    async def get_all_open_events(self, max_pages=50, series_ticker=None):
        return [
            e
            for e in self.events
            if any(m["status"] == "active" for m in e["markets"])
            and (not series_ticker or e["series_ticker"] == series_ticker)
        ]

    async def get_milestones(self, min_start, max_pages=30):
        return [m for m in self.milestones if _parse(m["start_date"]) >= min_start]

    async def get_event(self, event_ticker):
        for e in self.events:
            if e["event_ticker"] == event_ticker:
                event = {k: v for k, v in e.items() if k != "markets"}
                return {"event": event, "markets": e.get("markets", [])}
        raise KalshiError("Event not found", status_code=404)

    async def get_market(self, ticker, *, fresh=False):
        market = self._all_markets().get(ticker)
        if market is None:
            raise KalshiError("Market not found", status_code=404)
        return market

    async def get_markets(self, tickers, *, live=False):
        markets = self._all_markets()
        return [markets[t] for t in tickers if t in markets]

    async def get_orderbook(self, ticker, *, fresh=False):
        await self.get_market(ticker)
        return self.orderbooks.get(ticker, {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}})

    async def get_market_candlesticks(self, series_ticker, ticker, start_ts, end_ts, interval):
        market = await self.get_market(ticker)
        return fake_candles(ticker, market, start_ts, end_ts, interval)

    async def get_event_candlesticks(self, series_ticker, event_ticker, start_ts, end_ts, interval):
        data = await self.get_event(event_ticker)
        return {
            m["ticker"]: fake_candles(m["ticker"], m, start_ts, end_ts, interval)
            for m in data["markets"]
        }

    async def aclose(self):
        pass


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def fake_candles(ticker: str, market: dict, start_ts: int, end_ts: int, interval: int) -> list:
    """A deterministic random walk that ends at the market's current price."""
    step = interval * 60
    end = min(end_ts, int(time.time()))
    count = max(2, min(5000, (end - start_ts) // step))
    seed = int(hashlib.sha256(f"{ticker}:{interval}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    final = float(market.get("last_price_dollars") or 0.5)
    walk = [final]
    vol = 0.012 * math.sqrt(interval / 60)
    for _ in range(count - 1):
        walk.append(min(0.97, max(0.03, walk[-1] + rng.gauss(0, vol))))
    walk.reverse()
    first_end = end - (count - 1) * step
    candles = []
    for i, p in enumerate(walk):
        close = round(p, 2)
        candles.append(
            {
                "end_period_ts": first_end + i * step,
                "price": {"close_dollars": f"{close:.4f}", "mean_dollars": f"{close:.4f}"},
                "yes_bid": {"close_dollars": f"{max(0.01, close - 0.01):.4f}"},
                "yes_ask": {"close_dollars": f"{min(0.99, close + 0.01):.4f}"},
                "volume_fp": f"{rng.randint(0, 500)}.00",
            }
        )
    return candles


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
