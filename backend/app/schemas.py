from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Side = Literal["yes", "no"]
Action = Literal["buy", "sell"]

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# ---- auth ----
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_]+$")
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None
    cash: float


class ForgotPasswordIn(BaseModel):
    email: str = Field(max_length=255)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountIn(BaseModel):
    password: str


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
    close_time: datetime | None = None
    volume_24h: int = 0
    markets: list[MarketSummary]


class EventsPage(BaseModel):
    events: list[EventSummary]
    total: int
    page: int
    page_size: int
    has_more: bool


class CategoryCount(BaseModel):
    name: str
    count: int


class EventDetail(EventSummary):
    pass


class MarketDetail(MarketSummary):
    event_title: str
    series_ticker: str
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


class HistoryPoint(BaseModel):
    t: int  # unix seconds
    p: float  # YES price in dollars = implied probability


class MarketHistory(BaseModel):
    ticker: str
    range: str
    points: list[HistoryPoint]


class SeriesHistory(BaseModel):
    ticker: str
    label: str
    points: list[HistoryPoint]


class EventHistory(BaseModel):
    event_ticker: str
    range: str
    series: list[SeriesHistory]


# ---- trading ----
class TradeIn(BaseModel):
    ticker: str = Field(max_length=100)
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
    market_title: str = ""
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
    mark_price: float | None  # what you could sell at right now
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


class EquityPoint(BaseModel):
    day: date
    equity: float


# ---- leaderboard & leagues ----
class LeaderRow(BaseModel):
    rank: int
    username: str
    equity: float
    gain: float  # vs. starting cash (global) or vs. equity at join (league)
    gain_pct: float
    is_you: bool = False


class LeaderboardOut(BaseModel):
    rows: list[LeaderRow]
    you: LeaderRow | None
    total_players: int


class LeagueCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=500)


class LeagueJoin(BaseModel):
    invite_code: str = Field(min_length=4, max_length=12)


class LeagueSummary(BaseModel):
    id: int
    name: str
    description: str
    invite_code: str
    member_count: int
    is_owner: bool
    your_rank: int | None


class LeagueDetail(LeagueSummary):
    standings: list[LeaderRow]
