from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- accounts


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    cash_micros: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Bumped on password change/reset; tokens carrying an older version are rejected.
    token_version: Mapped[int] = mapped_column(Integer, default=0)

    positions: Mapped[list["Position"]] = relationship(back_populates="user")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- trading


class Position(Base):
    """A user's holding of one side (YES or NO) of one market."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "ticker", "side"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(100), index=True)
    side: Mapped[str] = mapped_column(String(3))  # "yes" | "no"
    market_title: Mapped[str] = mapped_column(String(300), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)  # basis of contracts still held
    realized_pnl_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(10), default="open")  # "open" | "settled"
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="positions")


class Trade(Base):
    """Immutable ledger of every buy, sell, and settlement."""

    __tablename__ = "trades"
    __table_args__ = (Index("ix_trades_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ticker: Mapped[str] = mapped_column(String(100))
    side: Mapped[str] = mapped_column(String(3))
    action: Mapped[str] = mapped_column(String(10))  # "buy" | "sell" | "settle"
    quantity: Mapped[int] = mapped_column(Integer)
    avg_price_micros: Mapped[int] = mapped_column(BigInteger)
    total_micros: Mapped[int] = mapped_column(BigInteger)
    realized_pnl_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EquitySnapshot(Base):
    """One row per user per day, updated by the worker, for the portfolio chart."""

    __tablename__ = "equity_snapshots"
    __table_args__ = (UniqueConstraint("user_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    equity_micros: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ---------------------------------------------------------------- market catalog
# A local copy of Kalshi's markets, refreshed by the worker, so search, sorting,
# and leaderboards never have to page through Kalshi on a user request.


class SyncedEvent(Base):
    __tablename__ = "synced_events"

    event_ticker: Mapped[str] = mapped_column(String(100), primary_key=True)
    series_ticker: Mapped[str] = mapped_column(String(100), default="", index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    sub_title: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(100), default="Other", index=True)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    volume_24h: Mapped[int] = mapped_column(BigInteger, default=0)
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SyncedMarket(Base):
    __tablename__ = "synced_markets"

    ticker: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_ticker: Mapped[str] = mapped_column(String(100), index=True)
    label: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="", index=True)
    result: Mapped[str] = mapped_column(String(10), default="")
    yes_bid: Mapped[int | None] = mapped_column(BigInteger)  # micros
    yes_ask: Mapped[int | None] = mapped_column(BigInteger)
    no_bid: Mapped[int | None] = mapped_column(BigInteger)
    no_ask: Mapped[int | None] = mapped_column(BigInteger)
    last_price: Mapped[int | None] = mapped_column(BigInteger)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    volume_24h: Mapped[int] = mapped_column(BigInteger, default=0)
    open_interest: Mapped[int] = mapped_column(BigInteger, default=0)
    open_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ---------------------------------------------------------------- leagues


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    invite_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    members: Mapped[list["LeagueMember"]] = relationship(
        back_populates="league", cascade="all, delete-orphan"
    )


class LeagueMember(Base):
    """Members are ranked by how much their account value has changed since joining."""

    __tablename__ = "league_members"
    __table_args__ = (UniqueConstraint("league_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    starting_equity_micros: Mapped[int] = mapped_column(BigInteger)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    league: Mapped[League] = relationship(back_populates="members")
    user: Mapped[User] = relationship()
