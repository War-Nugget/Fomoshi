import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.kalshi.client import KalshiClient, get_kalshi
from app.models import Position, Trade, User
from app.money import MICROS, to_dollars, to_micros
from app.ratelimit import rate_limit
from app.schemas import FillOut, PreviewOut, TradeIn, TradeOut, TradeResult
from app.trading.engine import execute_trade
from app.trading.orderbook import parse_orderbook, simulate_fill

router = APIRouter(prefix="/api/trades", tags=["trades"])


def trade_out(t: Trade, title: str = "") -> TradeOut:
    return TradeOut(
        id=t.id,
        ticker=t.ticker,
        market_title=title,
        side=t.side,
        action=t.action,
        quantity=t.quantity,
        avg_price=to_dollars(t.avg_price_micros),
        total=to_dollars(t.total_micros),
        realized_pnl=to_dollars(t.realized_pnl_micros),
        created_at=t.created_at,
    )


@router.post(
    "/preview", response_model=PreviewOut, dependencies=[Depends(rate_limit("preview", 120, 60))]
)
async def preview(body: TradeIn, kalshi: KalshiClient = Depends(get_kalshi)):
    """What this order would fill at right now, without placing it."""
    book = parse_orderbook(await kalshi.get_orderbook(body.ticker))
    fill = simulate_fill(book, body.side, body.action, body.quantity, to_micros(body.limit_price))
    return PreviewOut(
        filled_quantity=fill.filled,
        unfilled_quantity=fill.unfilled,
        avg_price=to_dollars(fill.avg_price),
        total=to_dollars(fill.total),
        fills=[FillOut(price=to_dollars(f.price), quantity=f.quantity) for f in fill.fills],
        max_payout=to_dollars(fill.filled * MICROS),
    )


@router.post(
    "",
    response_model=TradeResult,
    status_code=201,
    dependencies=[Depends(rate_limit("trade", 60, 60))],
)
async def place_trade(
    body: TradeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    kalshi: KalshiClient = Depends(get_kalshi),
):
    # Skip the cache: a book even a few seconds old lets someone watching a live game
    # buy at a price the real market has already moved past, or trade a market that
    # closed when the final whistle went.
    market, raw_book = await asyncio.gather(
        kalshi.get_market(body.ticker, fresh=True),
        kalshi.get_orderbook(body.ticker, fresh=True),
    )
    book = parse_orderbook(raw_book)
    trade, fill, user = execute_trade(
        db,
        user,
        market,
        book,
        side=body.side,
        action=body.action,
        quantity=body.quantity,
        limit_price=to_micros(body.limit_price),
    )
    return TradeResult(
        trade=trade_out(trade), unfilled_quantity=fill.unfilled, cash=to_dollars(user.cash_micros)
    )


@router.get("", response_model=list[TradeOut])
def history(
    limit: int = Query(100, ge=1, le=500),
    before_id: int | None = Query(None, description="Return trades older than this id"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Trade).where(Trade.user_id == user.id)
    if before_id:
        q = q.where(Trade.id < before_id)
    trades = db.scalars(q.order_by(Trade.id.desc()).limit(limit)).all()
    titles = dict(
        db.execute(
            select(Position.ticker, Position.market_title).where(Position.user_id == user.id)
        ).all()
    )
    return [trade_out(t, titles.get(t.ticker, "")) for t in trades]
