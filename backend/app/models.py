from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    cash_micros: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    positions: Mapped[list["Position"]] = relationship(back_populates="user")


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

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(100))
    side: Mapped[str] = mapped_column(String(3))
    action: Mapped[str] = mapped_column(String(10))  # "buy" | "sell" | "settle"
    quantity: Mapped[int] = mapped_column(Integer)
    avg_price_micros: Mapped[int] = mapped_column(BigInteger)
    total_micros: Mapped[int] = mapped_column(BigInteger)
    realized_pnl_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
