"""Keeps a local copy of Kalshi's open markets in the database."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import SyncedEvent, SyncedMarket
from app.money import to_contracts, to_micros

TRADABLE_STATUSES = {"active", "open"}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def market_label(market: dict) -> str:
    return market.get("yes_sub_title") or market.get("title") or market["ticker"]


def _market_fields(m: dict) -> dict:
    return {
        "event_ticker": m.get("event_ticker", ""),
        "label": market_label(m)[:500],
        "status": m.get("status", ""),
        "result": m.get("result") or "",
        "yes_bid": to_micros(m.get("yes_bid_dollars")),
        "yes_ask": to_micros(m.get("yes_ask_dollars")),
        "no_bid": to_micros(m.get("no_bid_dollars")),
        "no_ask": to_micros(m.get("no_ask_dollars")),
        "last_price": to_micros(m.get("last_price_dollars")),
        "volume": to_contracts(m.get("volume_fp")),
        "volume_24h": to_contracts(m.get("volume_24h_fp")),
        "open_interest": to_contracts(m.get("open_interest_fp")),
        "open_time": parse_time(m.get("open_time")),
        "close_time": parse_time(m.get("close_time")),
    }


def _upsert(db: Session, model, key: str, rows: dict[str, dict], now: datetime) -> None:
    keys = list(rows)
    for i in range(0, len(keys), 500):
        chunk = keys[i : i + 500]
        existing = {
            getattr(obj, key): obj
            for obj in db.scalars(select(model).where(getattr(model, key).in_(chunk)))
        }
        for k in chunk:
            obj = existing.get(k)
            if obj is None:
                obj = model(**{key: k})
                db.add(obj)
            for field, value in rows[k].items():
                setattr(obj, field, value)
            obj.synced_at = now


def upsert_markets(db: Session, markets: list[dict], now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    _upsert(db, SyncedMarket, "ticker", {m["ticker"]: _market_fields(m) for m in markets}, now)


def upsert_events(db: Session, events: list[dict], *, complete: bool) -> int:
    """Store events and their nested markets. When `complete` is true (we saw every open
    event), markets we didn't see are marked inactive so they drop out of listings."""
    now = datetime.now(UTC)
    event_rows: dict[str, dict] = {}
    markets: list[dict] = []
    for e in events:
        nested = e.get("markets") or []
        open_markets = [m for m in nested if m.get("status") in TRADABLE_STATUSES]
        closes = [t for m in open_markets if (t := parse_time(m.get("close_time")))]
        event_rows[e["event_ticker"]] = {
            "series_ticker": e.get("series_ticker", ""),
            "title": (e.get("title") or e["event_ticker"])[:500],
            "sub_title": (e.get("sub_title") or "")[:500],
            "category": e.get("category") or "Other",
            "volume": sum(to_contracts(m.get("volume_fp")) for m in nested),
            "volume_24h": sum(to_contracts(m.get("volume_24h_fp")) for m in nested),
            "close_time": min(closes) if closes else None,
        }
        markets.extend({**m, "event_ticker": e["event_ticker"]} for m in nested)

    _upsert(db, SyncedEvent, "event_ticker", event_rows, now)
    upsert_markets(db, markets, now)
    db.flush()
    if complete:
        db.execute(
            update(SyncedMarket)
            .where(SyncedMarket.status.in_(TRADABLE_STATUSES), SyncedMarket.synced_at < now)
            .values(status="inactive")
        )
    db.commit()
    return len(markets)
