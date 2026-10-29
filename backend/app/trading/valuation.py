"""Marks positions to market and computes account value (equity)."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Position, SyncedMarket, User
from app.money import MICROS


def mark_price(side: str, yes_bid: int | None, no_bid: int | None, last_price: int | None) -> int:
    """What one contract of `side` is worth now: the best bid (what you could sell for),
    falling back to the last traded price when nobody is bidding."""
    bid = yes_bid if side == "yes" else no_bid
    if bid:
        return bid
    if last_price:
        return last_price if side == "yes" else MICROS - last_price
    return 0


def mark_from_market_dict(side: str, market: dict) -> int:
    from app.money import to_micros

    return mark_price(
        side,
        to_micros(market.get("yes_bid_dollars")),
        to_micros(market.get("no_bid_dollars")),
        to_micros(market.get("last_price_dollars")),
    )


def equity_by_user(db: Session, user_ids: list[int] | None = None) -> dict[int, int]:
    """Cash + open positions marked with the synced catalog, for many users at once.
    Positions whose market isn't in the catalog are valued at cost."""
    users_q = select(User.id, User.cash_micros)
    pos_q = select(Position).where(Position.status == "open", Position.quantity > 0)
    if user_ids is not None:
        users_q = users_q.where(User.id.in_(user_ids))
        pos_q = pos_q.where(Position.user_id.in_(user_ids))

    equity = {uid: cash for uid, cash in db.execute(users_q)}
    positions = db.scalars(pos_q).all()
    tickers = list({p.ticker for p in positions})
    markets: dict[str, SyncedMarket] = {}
    for i in range(0, len(tickers), 500):
        for m in db.scalars(
            select(SyncedMarket).where(SyncedMarket.ticker.in_(tickers[i : i + 500]))
        ):
            markets[m.ticker] = m

    held: dict[int, int] = defaultdict(int)
    for p in positions:
        m = markets.get(p.ticker)
        value = (
            mark_price(p.side, m.yes_bid, m.no_bid, m.last_price) * p.quantity
            if m
            else p.cost_micros
        )
        held[p.user_id] += value
    return {uid: cash + held[uid] for uid, cash in equity.items()}
