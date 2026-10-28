"""Order book parsing and fill simulation. Pure functions, no database or network.

Kalshi only publishes *bids* for each side. Because YES + NO always pays $1,
a NO bid at price p is the same as a YES offer at $1 - p, and vice versa:

    best YES ask = $1 - best NO bid
    best NO ask  = $1 - best YES bid

So buying YES walks the NO bids from highest to lowest, and selling YES walks
the YES bids from highest to lowest.
"""

from dataclasses import dataclass, field

from app.money import MICROS, to_contracts, to_micros


@dataclass(frozen=True)
class Level:
    price: int  # micros
    quantity: int  # contracts


@dataclass
class OrderBook:
    yes_bids: list[Level]  # best (highest) first
    no_bids: list[Level]  # best (highest) first

    def bids(self, side: str) -> list[Level]:
        return self.yes_bids if side == "yes" else self.no_bids

    def asks(self, side: str) -> list[Level]:
        """Offers to sell `side`, cheapest first, derived from the other side's bids."""
        opposite = self.no_bids if side == "yes" else self.yes_bids
        return [Level(MICROS - lvl.price, lvl.quantity) for lvl in opposite]

    def best_bid(self, side: str) -> int | None:
        bids = self.bids(side)
        return bids[0].price if bids else None

    def best_ask(self, side: str) -> int | None:
        asks = self.asks(side)
        return asks[0].price if asks else None


def parse_orderbook(raw: dict) -> OrderBook:
    """Parse Kalshi's `orderbook_fp` response. Levels arrive ascending by price as
    [price_dollars, count_fp] string pairs, and either side may be null when empty."""
    book = raw.get("orderbook_fp") or {}

    def side(key: str) -> list[Level]:
        levels = []
        for price, qty in book.get(key) or []:
            q = to_contracts(qty)
            p = to_micros(price)
            if q > 0 and p is not None and 0 < p < MICROS:
                levels.append(Level(p, q))
        return sorted(levels, key=lambda lvl: lvl.price, reverse=True)

    return OrderBook(yes_bids=side("yes_dollars"), no_bids=side("no_dollars"))


@dataclass
class FillResult:
    requested: int
    fills: list[Level] = field(default_factory=list)

    @property
    def filled(self) -> int:
        return sum(f.quantity for f in self.fills)

    @property
    def unfilled(self) -> int:
        return self.requested - self.filled

    @property
    def total(self) -> int:
        return sum(f.price * f.quantity for f in self.fills)

    @property
    def avg_price(self) -> int | None:
        return round(self.total / self.filled) if self.filled else None


def simulate_fill(
    book: OrderBook, side: str, action: str, quantity: int, limit_price: int | None = None
) -> FillResult:
    """Walk the book as an immediate-or-cancel order.

    buy  -> take the cheapest asks, never paying more than `limit_price`
    sell -> hit the highest bids, never accepting less than `limit_price`
    Anything that can't fill right away is left unfilled (not rested on the book).
    """
    if side not in ("yes", "no") or action not in ("buy", "sell"):
        raise ValueError("side must be yes/no and action must be buy/sell")

    levels = book.asks(side) if action == "buy" else book.bids(side)
    result = FillResult(requested=quantity)
    remaining = quantity
    for lvl in levels:
        if remaining == 0:
            break
        if limit_price is not None:
            if action == "buy" and lvl.price > limit_price:
                break
            if action == "sell" and lvl.price < limit_price:
                break
        take = min(remaining, lvl.quantity)
        result.fills.append(Level(lvl.price, take))
        remaining -= take
    return result
