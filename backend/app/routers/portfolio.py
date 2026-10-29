from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.db import get_db
from app.kalshi.client import KalshiClient, KalshiError, get_kalshi
from app.models import EquitySnapshot, Position, User
from app.money import to_dollars, to_micros
from app.schemas import EquityPoint, PortfolioOut, PositionOut
from app.trading.valuation import mark_from_market_dict

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


async def build_portfolio(db: Session, user: User, kalshi: KalshiClient) -> PortfolioOut:
    positions = db.scalars(
        select(Position)
        .where(Position.user_id == user.id)
        .order_by(Position.status, Position.updated_at.desc())
    ).all()

    open_tickers = sorted({p.ticker for p in positions if p.status == "open" and p.quantity})
    try:
        markets = {m["ticker"]: m for m in await kalshi.get_markets(open_tickers)}
    except KalshiError:
        markets = {}  # still show the portfolio; value positions at cost

    out: list[PositionOut] = []
    positions_value = 0
    for p in positions:
        if p.status == "open" and p.quantity == 0:
            continue  # fully sold; realized P&L lives in trade history
        mark = value = None
        if p.status == "open":
            market = markets.get(p.ticker)
            if market:
                mark = mark_from_market_dict(p.side, market)
                value = mark * p.quantity
            positions_value += value if value is not None else p.cost_micros
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


@router.get("", response_model=PortfolioOut)
async def portfolio(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    kalshi: KalshiClient = Depends(get_kalshi),
):
    return await build_portfolio(db, user, kalshi)


@router.get("/history", response_model=list[EquityPoint])
async def equity_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    kalshi: KalshiClient = Depends(get_kalshi),
):
    """Daily account value for the last year, with today's value computed live."""
    today = datetime.now(UTC).date()
    snaps = db.scalars(
        select(EquitySnapshot)
        .where(EquitySnapshot.user_id == user.id, EquitySnapshot.day >= today - timedelta(365))
        .order_by(EquitySnapshot.day)
    ).all()
    points = [EquityPoint(day=s.day, equity=to_dollars(s.equity_micros)) for s in snaps]
    points = [p for p in points if p.day != today]

    created = user.created_at.date() if user.created_at else today
    if not points and created < today:
        points.append(EquityPoint(day=created, equity=get_settings().starting_cash))
    live = await build_portfolio(db, user, kalshi)
    points.append(EquityPoint(day=today, equity=live.equity))
    return points
