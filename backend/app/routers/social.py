"""Global leaderboard and private leagues."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_optional_user
from app.config import get_settings
from app.db import get_db
from app.models import League, LeagueMember, User
from app.money import to_dollars, to_micros
from app.ratelimit import rate_limit
from app.schemas import (
    LeaderboardOut,
    LeaderRow,
    LeagueCreate,
    LeagueDetail,
    LeagueJoin,
    LeagueSummary,
)
from app.trading.valuation import equity_by_user

router = APIRouter(prefix="/api", tags=["leaderboard"])

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion
MAX_LEAGUES_PER_USER = 25
MAX_LEAGUE_MEMBERS = 200


def _row(rank: int, username: str, equity: int, base: int, you: bool) -> LeaderRow:
    gain = equity - base
    return LeaderRow(
        rank=rank,
        username=username,
        equity=to_dollars(equity),
        gain=to_dollars(gain),
        gain_pct=round(gain / base * 100, 2) if base else 0.0,
        is_you=you,
    )


@router.get("/leaderboard", response_model=LeaderboardOut)
def leaderboard(
    limit: int = 50,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    start = to_micros(get_settings().starting_cash)
    names = dict(db.execute(select(User.id, User.username)).all())
    equity = equity_by_user(db)
    ranked = sorted(equity.items(), key=lambda kv: (-kv[1], names[kv[0]].lower()))
    rows, you = [], None
    for i, (uid, eq) in enumerate(ranked, start=1):
        is_you = viewer is not None and uid == viewer.id
        row = _row(i, names[uid], eq, start, is_you)
        if i <= min(limit, 100):
            rows.append(row)
        if is_you:
            you = row
    return LeaderboardOut(rows=rows, you=you, total_players=len(ranked))


# ---------------------------------------------------------------- leagues


def _standings(db: Session, league: League, viewer_id: int) -> list[LeaderRow]:
    members = league.members
    equity = equity_by_user(db, [m.user_id for m in members])
    rows = sorted(
        members,
        key=lambda m: (
            -(equity.get(m.user_id, 0) - m.starting_equity_micros),
            m.user.username.lower(),
        ),
    )
    return [
        _row(
            i,
            m.user.username,
            equity.get(m.user_id, 0),
            m.starting_equity_micros,
            m.user_id == viewer_id,
        )
        for i, m in enumerate(rows, start=1)
    ]


def _summary(league: League, standings: list[LeaderRow], viewer_id: int) -> LeagueSummary:
    return LeagueSummary(
        id=league.id,
        name=league.name,
        description=league.description,
        invite_code=league.invite_code,
        member_count=len(league.members),
        is_owner=league.owner_id == viewer_id,
        your_rank=next((r.rank for r in standings if r.is_you), None),
    )


def _get_member_league(db: Session, league_id: int, user: User) -> League:
    league = db.get(League, league_id)
    if league is None or all(m.user_id != user.id for m in league.members):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "League not found")
    return league


def _add_member(db: Session, league: League, user: User) -> None:
    start = equity_by_user(db, [user.id]).get(user.id, user.cash_micros)
    db.add(LeagueMember(league_id=league.id, user_id=user.id, starting_equity_micros=start))


def _league_count(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).where(LeagueMember.user_id == user.id))


@router.get("/leagues", response_model=list[LeagueSummary])
def my_leagues(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    leagues = db.scalars(
        select(League)
        .join(LeagueMember, LeagueMember.league_id == League.id)
        .where(LeagueMember.user_id == user.id)
        .order_by(League.created_at.desc())
    ).all()
    return [_summary(lg, _standings(db, lg, user.id), user.id) for lg in leagues]


@router.post(
    "/leagues",
    response_model=LeagueDetail,
    status_code=201,
    dependencies=[Depends(rate_limit("league-create", 10, 3600))],
)
def create_league(
    body: LeagueCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if _league_count(db, user) >= MAX_LEAGUES_PER_USER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You're in the maximum number of leagues")
    for _ in range(5):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        if not db.scalar(select(League.id).where(League.invite_code == code)):
            break
    league = League(
        name=body.name.strip(),
        description=body.description.strip(),
        invite_code=code,
        owner_id=user.id,
    )
    db.add(league)
    db.flush()
    _add_member(db, league, user)
    db.commit()
    db.refresh(league)
    standings = _standings(db, league, user.id)
    return LeagueDetail(**_summary(league, standings, user.id).model_dump(), standings=standings)


@router.post(
    "/leagues/join",
    response_model=LeagueDetail,
    dependencies=[Depends(rate_limit("league-join", 20, 600))],
)
def join_league(
    body: LeagueJoin, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    code = body.invite_code.strip().upper()
    league = db.scalar(select(League).where(League.invite_code == code))
    if league is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No league has that invite code")
    if all(m.user_id != user.id for m in league.members):
        if len(league.members) >= MAX_LEAGUE_MEMBERS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That league is full")
        if _league_count(db, user) >= MAX_LEAGUES_PER_USER:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "You're in the maximum number of leagues"
            )
        _add_member(db, league, user)
        try:
            db.commit()
        except IntegrityError:  # double-click race: already a member
            db.rollback()
        db.refresh(league)
    standings = _standings(db, league, user.id)
    return LeagueDetail(**_summary(league, standings, user.id).model_dump(), standings=standings)


@router.get("/leagues/{league_id}", response_model=LeagueDetail)
def league_detail(
    league_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    league = _get_member_league(db, league_id, user)
    standings = _standings(db, league, user.id)
    return LeagueDetail(**_summary(league, standings, user.id).model_dump(), standings=standings)


@router.delete("/leagues/{league_id}/membership", status_code=204)
def leave_league(
    league_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Leave a league. If the owner leaves, the league is deleted."""
    league = _get_member_league(db, league_id, user)
    if league.owner_id == user.id:
        db.delete(league)
    else:
        member = next(m for m in league.members if m.user_id == user.id)
        db.delete(member)
    db.commit()
