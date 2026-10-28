from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.db import get_db
from app.kalshi.client import KalshiClient, KalshiError, get_kalshi
from app.models import Position, User
from app.money import to_dollars, to_micros
from app.schemas import PortfolioOut, PositionOut

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioOut)
async def portfolio(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    kalshi: KalshiClient = Depends(get_kalshi),
):
    positions = db.scalars(
        select(Position)
        .where(Position.user_id == user.id)
        .order_by(Position.status, Position.updated_at.desc())
    ).all()

    open_tickers = sorted({p.ticker for p in positions if p.status == "open" and p.quantity})
    try:
        markets = {m["ticker"]: m for m in await kalshi.get_markets(open_tickers)}
    except KalshiError:
        markets = {}  # still show the portfolio, just without live marks

    out: list[PositionOut] = []
    positions_value = 0
    for p in positions:
        if p.status == "open" and p.quantity == 0:
            continue  # fully sold; realized P&L lives in trade history
        mark = None
        market = markets.get(p.ticker)
        if p.status == "open" and market:
            mark = to_micros(market.get(f"{p.side}_bid_dollars")) or 0
        value = mark * p.quantity if mark is not None else None
        if value is not None:
            positions_value += value
        out.append(
            PositionOut(
                ticker=p.ticker,
                side=p.side,
                market_title=p.market_title,
                quantity=p.quantity,
                avg_cost=to_dollars(round(p.cost_micros / p.quantity)) if p.quantity else None,
                cost_basis=to_dollars(p.cost_micros),
                mark_price=to_dollars(mark),
                market_value=to_dollars(value),
                unrealized_pnl=to_dollars(value - p.cost_micros) if value is not None else None,
                realized_pnl=to_dollars(p.realized_pnl_micros),
                status=p.status,
            )
        )

    starting = to_micros(get_settings().starting_cash)
    equity = user.cash_micros + positions_value
    return PortfolioOut(
        cash=to_dollars(user.cash_micros),
        positions_value=to_dollars(positions_value),
        equity=to_dollars(equity),
        starting_cash=to_dollars(starting),
        total_pnl=to_dollars(equity - starting),
        positions=out,
    )
