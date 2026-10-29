"""Pays out positions once Kalshi settles a market. Called by the worker (app.worker)."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Position, Trade
from app.money import MICROS, to_micros
from app.trading.engine import lock_user

log = logging.getLogger("fomoshi.settlement")

SETTLED_STATUSES = {"determined", "amended", "finalized", "settled"}


def payout_per_contract(market: dict, side: str) -> int | None:
    """Micros paid per contract of `side`, or None if the market isn't settled yet."""
    if market.get("status") not in SETTLED_STATUSES:
        return None
    result = market.get("result")
    if result == "yes":
        yes = MICROS
    elif result == "no":
        yes = 0
    elif result == "scalar":
        yes = to_micros(market.get("settlement_value_dollars"))
        if yes is None:
            return None
    else:
        return None
    return yes if side == "yes" else MICROS - yes


def settle_markets(db: Session, markets: list[dict]) -> int:
    """Settle every open position in the given (already-fetched) markets.

    Safe to run repeatedly and from more than one process: each user's row is locked
    before their positions, and positions are re-read under the lock, so a position
    can only be paid once. Returns the number of positions settled.
    """
    settled_markets = {m["ticker"]: m for m in markets if payout_per_contract(m, "yes") is not None}
    if not settled_markets:
        return 0

    user_ids = db.scalars(
        select(Position.user_id)
        .where(Position.status == "open", Position.ticker.in_(list(settled_markets)))
        .distinct()
    ).all()

    count = 0
    for user_id in user_ids:
        user = lock_user(db, user_id)
        positions = db.scalars(
            select(Position)
            .where(
                Position.user_id == user_id,
                Position.status == "open",
                Position.ticker.in_(list(settled_markets)),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
        for pos in positions:
            payout = payout_per_contract(settled_markets[pos.ticker], pos.side)
            proceeds = payout * pos.quantity
            pnl = proceeds - pos.cost_micros
            user.cash_micros += proceeds
            db.add(
                Trade(
                    user_id=user_id,
                    ticker=pos.ticker,
                    side=pos.side,
                    action="settle",
                    quantity=pos.quantity,
                    avg_price_micros=payout,
                    total_micros=proceeds,
                    realized_pnl_micros=pnl,
                )
            )
            pos.realized_pnl_micros += pnl
            pos.quantity = 0
            pos.cost_micros = 0
            pos.status = "settled"
            count += 1
        db.commit()  # one transaction per user keeps locks short
    if count:
        log.info("settled %d positions", count)
    return count


def open_position_tickers(db: Session) -> list[str]:
    return list(db.scalars(select(Position.ticker).where(Position.status == "open").distinct()))
