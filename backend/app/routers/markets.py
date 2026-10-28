from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.kalshi.client import KalshiClient, KalshiError, get_kalshi
from app.money import to_contracts, to_dollars, to_micros
from app.schemas import (
    BookLevel,
    EventsPage,
    EventSummary,
    MarketDetail,
    MarketSummary,
    OrderBookOut,
)
from app.trading.engine import TRADABLE_STATUSES, market_label
from app.trading.orderbook import Level, parse_orderbook

router = APIRouter(prefix="/api/markets", tags=["markets"])


def _price(m: dict, key: str) -> float | None:
    return to_dollars(to_micros(m.get(key)))


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def summarize(m: dict) -> MarketSummary:
    return MarketSummary(
        ticker=m["ticker"],
        event_ticker=m.get("event_ticker", ""),
        label=market_label(m),
        status=m.get("status", ""),
        yes_bid=_price(m, "yes_bid_dollars"),
        yes_ask=_price(m, "yes_ask_dollars"),
        no_bid=_price(m, "no_bid_dollars"),
        no_ask=_price(m, "no_ask_dollars"),
        last_price=_price(m, "last_price_dollars"),
        volume=to_contracts(m.get("volume_fp")),
        volume_24h=to_contracts(m.get("volume_24h_fp")),
        open_interest=to_contracts(m.get("open_interest_fp")),
        close_time=_time(m.get("close_time")),
        result=m.get("result") or "",
    )


@router.get("", response_model=EventsPage)
async def list_events(
    q: str | None = Query(None, description="Search event titles and outcomes"),
    category: str | None = None,
    cursor: str | None = None,
    kalshi: KalshiClient = Depends(get_kalshi),
):
    data = await kalshi.get_events(cursor=cursor, limit=100)
    needle = (q or "").strip().lower()
    events: list[EventSummary] = []
    for e in data.get("events", []):
        markets = [
            summarize(m) for m in e.get("markets") or [] if m.get("status") in TRADABLE_STATUSES
        ]
        if not markets:
            continue
        cat = e.get("category") or "Other"
        if category and cat.lower() != category.lower():
            continue
        if needle:
            haystack = " ".join([e.get("title", ""), *(m.label for m in markets)]).lower()
            if needle not in haystack:
                continue
        markets.sort(key=lambda m: m.last_price or 0, reverse=True)
        events.append(
            EventSummary(
                event_ticker=e["event_ticker"],
                series_ticker=e.get("series_ticker", ""),
                title=e.get("title", e["event_ticker"]),
                sub_title=e.get("sub_title", ""),
                category=cat,
                markets=markets,
            )
        )
    return EventsPage(events=events, cursor=data.get("cursor") or None)


@router.get("/{ticker}", response_model=MarketDetail)
async def get_market(ticker: str, kalshi: KalshiClient = Depends(get_kalshi)):
    market = await kalshi.get_market(ticker)
    try:
        event = await kalshi.get_event(market["event_ticker"])
        event_title = event.get("title", "")
    except KalshiError:
        event_title = ""
    return MarketDetail(
        **summarize(market).model_dump(),
        event_title=event_title,
        rules_primary=market.get("rules_primary", ""),
    )


def _levels(levels: list[Level]) -> list[BookLevel]:
    return [BookLevel(price=to_dollars(lvl.price), quantity=lvl.quantity) for lvl in levels]


@router.get("/{ticker}/orderbook", response_model=OrderBookOut)
async def get_orderbook(ticker: str, kalshi: KalshiClient = Depends(get_kalshi)):
    book = parse_orderbook(await kalshi.get_orderbook(ticker))
    return OrderBookOut(
        ticker=ticker,
        yes_bids=_levels(book.bids("yes")),
        yes_asks=_levels(book.asks("yes")),
        no_bids=_levels(book.bids("no")),
        no_asks=_levels(book.asks("no")),
    )
