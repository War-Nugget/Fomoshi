"""Turns Kalshi candlesticks into simple [(timestamp, price)] series for charts."""

import time
from datetime import datetime
from typing import Literal

from app.money import MICROS, to_dollars

Range = Literal["1d", "1w", "1m", "all"]

# range -> (seconds of history or None for "since the market opened", candle minutes)
RANGES: dict[str, tuple[int | None, int]] = {
    "1d": (86_400, 1),
    "1w": (7 * 86_400, 60),
    "1m": (30 * 86_400, 60),
    "all": (None, 1440),
}
MAX_CANDLES = 4000


def window(range_: str, opened: datetime | None) -> tuple[int, int, int]:
    """(start_ts, end_ts, interval_minutes) for a chart range."""
    seconds, interval = RANGES[range_]
    end = int(time.time())
    if seconds is None:
        start = int(opened.timestamp()) if opened else end - 365 * 86_400
    else:
        start = end - seconds
    start = max(start, end - MAX_CANDLES * interval * 60)
    return start, end, interval


def _dollars(obj: object, field: str) -> int | None:
    """Read `field` from a candle sub-object in either Kalshi format:
    {"close_dollars": "0.4200"} or {"close": "0.4200"} / {"close": 42} (cents)."""
    if not isinstance(obj, dict):
        return None
    raw = obj.get(f"{field}_dollars")
    if raw is None:
        raw = obj.get(field)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw * MICROS // 100  # legacy integer cents
    if raw in (None, ""):
        return None
    try:
        return round(float(raw) * MICROS)
    except (TypeError, ValueError):
        return None


def candle_price(c: dict) -> int | None:
    """Last traded price in the candle, else the bid/ask midpoint."""
    price = _dollars(c.get("price"), "close")
    if price:
        return price
    bid = _dollars(c.get("yes_bid") or c.get("bid"), "close")
    ask = _dollars(c.get("yes_ask") or c.get("ask"), "close")
    if bid and ask:
        return (bid + ask) // 2
    return None


def to_points(candles: list[dict]) -> list[dict]:
    """[{t, p}] with gaps carried forward so the line is continuous."""
    points: list[dict] = []
    last: int | None = None
    for c in sorted(candles, key=lambda c: c.get("end_period_ts", 0)):
        p = candle_price(c)
        if p is None:
            if last is None:
                continue
            p = last
        if not 0 < p < MICROS:
            continue
        last = p
        points.append({"t": int(c["end_period_ts"]), "p": to_dollars(p)})
    return points
