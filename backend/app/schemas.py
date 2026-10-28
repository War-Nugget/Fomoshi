from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Side = Literal["yes", "no"]
Action = Literal["buy", "sell"]


# ---- auth ----
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    cash: float


# ---- markets ----
class MarketSummary(BaseModel):
    ticker: str
    event_ticker: str
    label: str  # short name of the YES outcome
    status: str
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None
    last_price: float | None
    volume: int
    volume_24h: int
    open_interest: int
    close_time: datetime | None
    result: str = ""


class EventSummary(BaseModel):
    event_ticker: str
    series_ticker: str
    title: str
    sub_title: str
    category: str
    markets: list[MarketSummary]


class EventsPage(BaseModel):
    events: list[EventSummary]
    cursor: str | None


class MarketDetail(MarketSummary):
    event_title: str
    rules_primary: str


class BookLevel(BaseModel):
    price: float
    quantity: int


class OrderBookOut(BaseModel):
    ticker: str
    yes_bids: list[BookLevel]  # best (highest) first
    yes_asks: list[BookLevel]  # best (lowest) first; derived from NO bids
    no_bids: list[BookLevel]
    no_asks: list[BookLevel]


# ---- trading ----
class TradeIn(BaseModel):
    ticker: str
    side: Side
    action: Action
    quantity: int = Field(gt=0, le=100_000)
    limit_price: float | None = Field(
        default=None, gt=0, lt=1, description="Worst price you will accept per contract"
    )


class FillOut(BaseModel):
    price: float
    quantity: int


class PreviewOut(BaseModel):
    filled_quantity: int
    unfilled_quantity: int
    avg_price: float | None
    total: float
    fills: list[FillOut]
    max_payout: float  # what the filled contracts pay if this side wins


class TradeOut(BaseModel):
    id: int
    ticker: str
    side: str
    action: str
    quantity: int
    avg_price: float
    total: float
    realized_pnl: float
    created_at: datetime


class TradeResult(BaseModel):
    trade: TradeOut
    unfilled_quantity: int
    cash: float


# ---- portfolio ----
class PositionOut(BaseModel):
    ticker: str
    side: str
    market_title: str
    quantity: int
    avg_cost: float | None
    cost_basis: float
    mark_price: float | None  # best bid for this side: what you could sell at right now
    market_value: float | None
    unrealized_pnl: float | None
    realized_pnl: float
    status: str


class PortfolioOut(BaseModel):
    cash: float
    positions_value: float
    equity: float
    starting_cash: float
    total_pnl: float
    positions: list[PositionOut]
