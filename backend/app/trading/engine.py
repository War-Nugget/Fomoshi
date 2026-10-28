"""Executes simulated trades against a snapshot of Kalshi's live order book."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Position, Trade, User
from app.trading.orderbook import FillResult, OrderBook, simulate_fill

TRADABLE_STATUSES = {"active", "open"}


class TradeError(Exception):
    pass


def market_label(market: dict) -> str:
    return market.get("yes_sub_title") or market.get("title") or market["ticker"]


def ensure_tradable(market: dict) -> None:
    if market.get("status") not in TRADABLE_STATUSES:
        raise TradeError("This market is not open for trading")
    close_time = market.get("close_time")
    if close_time:
        closes = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
        if closes <= datetime.now(UTC):
            raise TradeError("This market has closed")


def get_position(db: Session, user_id: int, ticker: str, side: str) -> Position | None:
    return db.scalar(
        select(Position).where(
            Position.user_id == user_id, Position.ticker == ticker, Position.side == side
        )
    )


def execute_trade(
    db: Session,
    user: User,
    market: dict,
    book: OrderBook,
    *,
    side: str,
    action: str,
    quantity: int,
    limit_price: int | None = None,
) -> tuple[Trade, FillResult]:
    ensure_tradable(market)
    ticker = market["ticker"]
    position = get_position(db, user.id, ticker, side)

    if action == "sell":
        held = position.quantity if position and position.status == "open" else 0
        if held < quantity:
            raise TradeError(f"You only hold {held} {side.upper()} contracts")

    fill = simulate_fill(book, side, action, quantity, limit_price)
    if fill.filled == 0:
        raise TradeError("No liquidity available at that price")

    realized = 0
    if action == "buy":
        if fill.total > user.cash_micros:
            raise TradeError("Not enough cash for this order")
        user.cash_micros -= fill.total
        if position is None:
            position = Position(
                user_id=user.id,
                ticker=ticker,
                side=side,
                market_title=market_label(market),
                quantity=0,
                cost_micros=0,
                realized_pnl_micros=0,
            )
            db.add(position)
        position.status = "open"
        position.quantity += fill.filled
        position.cost_micros += fill.total
    else:
        # average-cost accounting: remove the sold share of the basis
        basis_removed = position.cost_micros * fill.filled // position.quantity
        realized = fill.total - basis_removed
        user.cash_micros += fill.total
        position.quantity -= fill.filled
        position.cost_micros -= basis_removed
        position.realized_pnl_micros += realized

    trade = Trade(
        user_id=user.id,
        ticker=ticker,
        side=side,
        action=action,
        quantity=fill.filled,
        avg_price_micros=fill.avg_price,
        total_micros=fill.total,
        realized_pnl_micros=realized,
    )
    db.add(trade)
    db.commit()
    return trade, fill
