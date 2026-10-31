from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.catalog import TRADABLE_STATUSES
from app.config import get_settings
from app.db import get_db
from app.games import GAME_LOOKBACK
from app.kalshi.client import KalshiClient, get_kalshi
from app.models import SyncedGame
from app.routers.markets import _aware, summarize
from app.schemas import CategoryCount, GameOut, GamesPage

router = APIRouter(prefix="/api/games", tags=["games"])


def _in_window(now: datetime):
    """Games that may still be on, through the lookahead horizon."""
    horizon = now + timedelta(hours=get_settings().games_lookahead_hours)
    return SyncedGame.start_time >= now - GAME_LOOKBACK, SyncedGame.start_time <= horizon


@router.get("", response_model=GamesPage)
async def list_games(
    league: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1, le=100),
    page_size: int = Query(24, ge=1, le=96),
    db: Session = Depends(get_db),
    kalshi: KalshiClient = Depends(get_kalshi),
):
    """Live games (busiest first), then upcoming games by start time. The schedule comes
    from the database; prices come from Kalshi on every call, cached for seconds."""
    now = datetime.now(UTC)
    started = SyncedGame.start_time <= now
    stmt = select(SyncedGame).where(*_in_window(now))
    if league:
        stmt = stmt.where(func.lower(SyncedGame.league) == league.lower())
    stmt = stmt.order_by(
        case((started, 0), else_=1),
        case((started, -SyncedGame.volume_24h), else_=0),
        SyncedGame.start_time,
        SyncedGame.event_ticker,
    )
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()

    tickers = [t for g in rows for t in (g.team_a_ticker, g.team_b_ticker, g.tie_ticker) if t]
    markets = {m["ticker"]: m for m in await kalshi.get_markets(tickers, live=True)}

    games: list[GameOut] = []
    for g in rows:
        a, b = markets.get(g.team_a_ticker), markets.get(g.team_b_ticker)
        if not a or not b or not {a.get("status"), b.get("status")} & TRADABLE_STATUSES:
            continue  # finished since the last schedule sync
        tie = markets.get(g.tie_ticker)
        start = _aware(g.start_time)
        games.append(
            GameOut(
                event_ticker=g.event_ticker,
                series_ticker=g.series_ticker,
                league=g.league,
                title=g.title,
                start_time=start,
                live=start <= now,
                team_a=summarize({**a, "event_ticker": g.event_ticker}),
                team_b=summarize({**b, "event_ticker": g.event_ticker}),
                tie=summarize({**tie, "event_ticker": g.event_ticker}) if tie else None,
                volume_24h=g.volume_24h,
            )
        )
    return GamesPage(
        games=games,
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
    )


@router.get("/leagues", response_model=list[CategoryCount])
def leagues(db: Session = Depends(get_db)):
    """Leagues with games in the window, busiest first."""
    rows = db.execute(
        select(SyncedGame.league, func.count())
        .where(*_in_window(datetime.now(UTC)))
        .group_by(SyncedGame.league)
        .order_by(func.sum(SyncedGame.volume_24h).desc(), SyncedGame.league)
    ).all()
    return [CategoryCount(name=name, count=n) for name, n in rows]
