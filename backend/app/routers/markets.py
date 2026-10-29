from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.catalog import TRADABLE_STATUSES, market_label, parse_time
from app.db import get_db
from app.history import Range, to_points, window
from app.kalshi.client import KalshiClient, KalshiError, get_kalshi
from app.models import SyncedEvent, SyncedMarket
from app.money import to_contracts, to_dollars, to_micros
from app.schemas import (
    BookLevel,
    CategoryCount,
    EventDetail,
    EventHistory,
    EventsPage,
    EventSummary,
    MarketDetail,
    MarketHistory,
    MarketSummary,
    OrderBookOut,
    SeriesHistory,
)
from app.trading.orderbook import Level, parse_orderbook

router = APIRouter(prefix="/api", tags=["markets"])

Sort = Literal["trending", "volume", "closing", "new"]
EVENT_CHART_MAX_LINES = 6


# ---------------------------------------------------------------- converters


def _price(m: dict, key: str) -> float | None:
    return to_dollars(to_micros(m.get(key)))


def summarize(m: dict) -> MarketSummary:
    """From a raw Kalshi market dict."""
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
        close_time=parse_time(m.get("close_time")),
        result=m.get("result") or "",
    )


def summarize_row(m: SyncedMarket) -> MarketSummary:
    """From a synced catalog row."""
    return MarketSummary(
        ticker=m.ticker,
        event_ticker=m.event_ticker,
        label=m.label,
        status=m.status,
        yes_bid=to_dollars(m.yes_bid),
        yes_ask=to_dollars(m.yes_ask),
        no_bid=to_dollars(m.no_bid),
        no_ask=to_dollars(m.no_ask),
        last_price=to_dollars(m.last_price),
        volume=m.volume,
        volume_24h=m.volume_24h,
        open_interest=m.open_interest,
        close_time=_aware(m.close_time),
        result=m.result,
    )


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def _by_price(markets: list[MarketSummary]) -> list[MarketSummary]:
    return sorted(markets, key=lambda m: m.last_price or 0, reverse=True)


# ---------------------------------------------------------------- listing


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/markets", response_model=EventsPage)
async def list_events(
    q: str | None = Query(None, max_length=100, description="Search titles and outcomes"),
    category: str | None = Query(None, max_length=100),
    sort: Sort = "trending",
    page: int = Query(1, ge=1, le=500),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    kalshi: KalshiClient = Depends(get_kalshi),
):
    if db.scalar(select(func.count()).select_from(SyncedEvent)) == 0:
        # Catalog not synced yet (first boot): fall back to one live page from Kalshi.
        return await _live_page(kalshi, q, category, page_size)

    open_market = exists().where(
        SyncedMarket.event_ticker == SyncedEvent.event_ticker,
        SyncedMarket.status.in_(TRADABLE_STATUSES),
    )
    stmt = select(SyncedEvent).where(open_market)
    if category:
        stmt = stmt.where(func.lower(SyncedEvent.category) == category.lower())
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        label_match = exists().where(
            SyncedMarket.event_ticker == SyncedEvent.event_ticker,
            SyncedMarket.status.in_(TRADABLE_STATUSES),
            SyncedMarket.label.ilike(pattern, escape="\\"),
        )
        stmt = stmt.where(or_(SyncedEvent.title.ilike(pattern, escape="\\"), label_match))
    if sort == "closing":
        stmt = stmt.where(SyncedEvent.close_time > datetime.now(UTC)).order_by(
            SyncedEvent.close_time.asc()
        )
    elif sort == "volume":
        stmt = stmt.order_by(SyncedEvent.volume.desc())
    elif sort == "new":
        stmt = stmt.order_by(SyncedEvent.first_seen_at.desc())
    else:
        stmt = stmt.order_by(SyncedEvent.volume_24h.desc(), SyncedEvent.volume.desc())
    stmt = stmt.order_by(SyncedEvent.event_ticker)

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    events = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()

    markets: dict[str, list[MarketSummary]] = {e.event_ticker: [] for e in events}
    if events:
        for m in db.scalars(
            select(SyncedMarket).where(
                SyncedMarket.event_ticker.in_(list(markets)),
                SyncedMarket.status.in_(TRADABLE_STATUSES),
            )
        ):
            markets[m.event_ticker].append(summarize_row(m))

    return EventsPage(
        events=[
            EventSummary(
                event_ticker=e.event_ticker,
                series_ticker=e.series_ticker,
                title=e.title,
                sub_title=e.sub_title,
                category=e.category,
                close_time=_aware(e.close_time),
                volume_24h=e.volume_24h,
                markets=_by_price(markets[e.event_ticker]),
            )
            for e in events
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
    )


async def _live_page(kalshi: KalshiClient, q, category, page_size) -> EventsPage:
    data = await kalshi.get_events(limit=100)
    needle = (q or "").strip().lower()
    out: list[EventSummary] = []
    for e in data.get("events", []):
        ms = [summarize(m) for m in e.get("markets") or [] if m.get("status") in TRADABLE_STATUSES]
        cat = e.get("category") or "Other"
        if not ms or (category and cat.lower() != category.lower()):
            continue
        text = " ".join([e.get("title", ""), *(m.label for m in ms)]).lower()
        if needle and needle not in text:
            continue
        out.append(
            EventSummary(
                event_ticker=e["event_ticker"],
                series_ticker=e.get("series_ticker", ""),
                title=e.get("title", e["event_ticker"]),
                sub_title=e.get("sub_title", ""),
                category=cat,
                markets=_by_price(ms),
            )
        )
    return EventsPage(
        events=out[:page_size], total=len(out), page=1, page_size=page_size, has_more=False
    )


@router.get("/markets/categories", response_model=list[CategoryCount])
def categories(db: Session = Depends(get_db)):
    open_market = exists().where(
        SyncedMarket.event_ticker == SyncedEvent.event_ticker,
        SyncedMarket.status.in_(TRADABLE_STATUSES),
    )
    rows = db.execute(
        select(SyncedEvent.category, func.count())
        .where(open_market)
        .group_by(SyncedEvent.category)
        .order_by(func.count().desc())
    ).all()
    return [CategoryCount(name=name, count=n) for name, n in rows]


# ---------------------------------------------------------------- one market


async def _event_info(kalshi: KalshiClient, event_ticker: str) -> dict:
    try:
        return (await kalshi.get_event(event_ticker))["event"]
    except KalshiError:
        return {}


@router.get("/markets/{ticker}", response_model=MarketDetail)
async def get_market(ticker: str, kalshi: KalshiClient = Depends(get_kalshi)):
    market = await kalshi.get_market(ticker)
    event = await _event_info(kalshi, market.get("event_ticker", ""))
    return MarketDetail(
        **summarize(market).model_dump(),
        event_title=event.get("title", ""),
        series_ticker=event.get("series_ticker", ""),
        rules_primary=market.get("rules_primary", ""),
    )


def _levels(levels: list[Level]) -> list[BookLevel]:
    return [BookLevel(price=to_dollars(lvl.price), quantity=lvl.quantity) for lvl in levels]


@router.get("/markets/{ticker}/orderbook", response_model=OrderBookOut)
async def get_orderbook(ticker: str, kalshi: KalshiClient = Depends(get_kalshi)):
    book = parse_orderbook(await kalshi.get_orderbook(ticker))
    return OrderBookOut(
        ticker=ticker,
        yes_bids=_levels(book.bids("yes")),
        yes_asks=_levels(book.asks("yes")),
        no_bids=_levels(book.bids("no")),
        no_asks=_levels(book.asks("no")),
    )


@router.get("/markets/{ticker}/history", response_model=MarketHistory)
async def market_history(
    ticker: str, range: Range = "1w", kalshi: KalshiClient = Depends(get_kalshi)
):
    market = await kalshi.get_market(ticker)
    event = await _event_info(kalshi, market.get("event_ticker", ""))
    series = event.get("series_ticker")
    if not series:
        return MarketHistory(ticker=ticker, range=range, points=[])
    start, end, interval = window(range, parse_time(market.get("open_time")))
    candles = await kalshi.get_market_candlesticks(series, ticker, start, end, interval)
    return MarketHistory(ticker=ticker, range=range, points=to_points(candles))


# ---------------------------------------------------------------- one event


@router.get("/events/{event_ticker}", response_model=EventDetail)
async def get_event(event_ticker: str, kalshi: KalshiClient = Depends(get_kalshi)):
    data = await kalshi.get_event(event_ticker)
    e = data["event"]
    markets = [summarize({**m, "event_ticker": event_ticker}) for m in data["markets"]]
    open_markets = [m for m in markets if m.status in TRADABLE_STATUSES]
    closes = [m.close_time for m in open_markets if m.close_time]
    return EventDetail(
        event_ticker=event_ticker,
        series_ticker=e.get("series_ticker", ""),
        title=e.get("title", event_ticker),
        sub_title=e.get("sub_title", ""),
        category=e.get("category") or "Other",
        close_time=min(closes) if closes else None,
        volume_24h=sum(m.volume_24h for m in markets),
        markets=_by_price(open_markets) + [m for m in markets if m not in open_markets],
    )


@router.get("/events/{event_ticker}/history", response_model=EventHistory)
async def event_history(
    event_ticker: str, range: Range = "1w", kalshi: KalshiClient = Depends(get_kalshi)
):
    data = await kalshi.get_event(event_ticker)
    series = data["event"].get("series_ticker")
    markets = sorted(
        (m for m in data["markets"] if m.get("status") in TRADABLE_STATUSES),
        key=lambda m: to_micros(m.get("last_price_dollars")) or 0,
        reverse=True,
    )[:EVENT_CHART_MAX_LINES]
    if not series or not markets:
        return EventHistory(event_ticker=event_ticker, range=range, series=[])
    opened = min((t for m in markets if (t := parse_time(m.get("open_time")))), default=None)
    start, end, interval = window(range, opened)
    candles = await kalshi.get_event_candlesticks(series, event_ticker, start, end, interval)
    return EventHistory(
        event_ticker=event_ticker,
        range=range,
        series=[
            SeriesHistory(
                ticker=m["ticker"],
                label=market_label(m),
                points=to_points(candles.get(m["ticker"], [])),
            )
            for m in markets
        ],
    )
