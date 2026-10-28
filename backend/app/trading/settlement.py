"""Pays out positions once Kalshi settles a market.

Runs on a timer inside the API process (see app.main), and can also be run on its
own, e.g. from cron:  python -m app.trading.settlement
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kalshi.client import KalshiClient, KalshiError
from app.models import Position, Trade, User
from app.money import MICROS, to_micros

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
    Returns the number of positions settled. Safe to run repeatedly."""
    by_ticker = {m["ticker"]: m for m in markets}
    positions = db.scalars(
        select(Position).where(Position.status == "open", Position.ticker.in_(list(by_ticker)))
    ).all()

    settled = 0
    for pos in positions:
        payout = payout_per_contract(by_ticker[pos.ticker], pos.side)
        if payout is None:
            continue
        user = db.get(User, pos.user_id)
        proceeds = payout * pos.quantity
        pnl = proceeds - pos.cost_micros
        user.cash_micros += proceeds
        db.add(
            Trade(
                user_id=pos.user_id,
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
        settled += 1
    db.commit()
    return settled


async def run_settlement_once(db: Session, kalshi: KalshiClient) -> int:
    tickers = list(db.scalars(select(Position.ticker).where(Position.status == "open").distinct()))
    if not tickers:
        return 0
    try:
        markets = await kalshi.get_markets(tickers)
    except KalshiError as exc:
        log.warning("settlement skipped: %s", exc)
        return 0
    count = settle_markets(db, markets)
    if count:
        log.info("settled %d positions", count)
    return count


async def settlement_loop(interval: int) -> None:
    from app.db import SessionLocal
    from app.kalshi.client import get_kalshi

    while True:
        try:
            with SessionLocal() as db:
                await run_settlement_once(db, get_kalshi())
        except Exception:  # keep the loop alive no matter what
            log.exception("settlement run failed")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    from app.db import SessionLocal, init_db
    from app.kalshi.client import get_kalshi

    logging.basicConfig(level=logging.INFO)
    init_db()

    async def _main():
        with SessionLocal() as db:
            n = await run_settlement_once(db, get_kalshi())
        print(f"Settled {n} positions")

    asyncio.run(_main())
