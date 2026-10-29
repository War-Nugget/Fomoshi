"""Executes simulated trades against a snapshot of Kalshi's live order book."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import TRADABLE_STATUSES, market_label, parse_time
from app.models import Position, Trade, User
from app.trading.orderbook import FillResult, OrderBook, simulate_fill


class TradeError(Exception):
    pass


def ensure_tradable(market: dict) -> None:
    if market.get("status") not in TRADABLE_STATUSES:
        raise TradeError("This market is not open for trading")
    closes = parse_time(market.get("close_time"))
    if closes and closes <= datetime.now(UTC):
        raise TradeError("This market has closed")


def lock_user(db: Session, user_id: int) -> User:
    """Load the user row with SELECT ... FOR UPDATE so two orders from the same
    account can't both spend the same cash. (SQLite ignores the lock; it only
    allows one writer at a time anyway.)"""
    return db.execute(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()


def get_position(db: Session, user_id: int, ticker: str, side: str, *, lock=False):
    q = select(Position).where(
        Position.user_id == user_id, Position.ticker == ticker, Position.side == side
    )
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    return db.scalar(q)


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
) -> tuple[Trade, FillResult, User]:
    ensure_tradable(market)
    ticker = market["ticker"]
    try:
        user = lock_user(db, user.id)  # always lock the user first, then positions
        position = get_position(db, user.id, ticker, side, lock=True)

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
                    market_title=market_label(market)[:300],
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
    except Exception:
        db.rollback()
        raise
    return trade, fill, user
