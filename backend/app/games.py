"""Finds head-to-head games ("Team A vs Team B") and keeps them in the database.

Today's games sit thousands of events deep in Kalshi's catalog listing, past where the
catalog sync stops, so games are found through Kalshi's sports schedule instead. Each
schedule entry ("milestone") has a start time and names its game's event. That event
counts as a game when Kalshi tags it with competition_scope "Game" and it has exactly
two sides, plus a "-TIE" market in sports where a draw is possible.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.catalog import market_label
from app.models import SyncedGame
from app.money import to_contracts

# A game that started this long ago may still be on (cricket, extra innings, delays).
# Finished games drop out sooner: their markets close once a winner is declared.
GAME_LOOKBACK = timedelta(hours=12)


def series_of(event_ticker: str) -> str:
    """Kalshi event tickers start with their series ticker: KXNBAGAME-26OCT30HOUDAL."""
    return event_ticker.split("-", 1)[0]


def milestone_event_tickers(milestone: dict) -> list[str]:
    main = (milestone.get("details") or {}).get("main_game_event_ticker")
    return [main] if main else list(milestone.get("primary_event_tickers") or [])


def _names(label: str, name: str) -> bool:
    """True when a market's label is this title name. Titles sometimes use surnames
    ("Tudorica vs Colin") where markets have full names ("Alvin Nicholas Tudorica")."""
    label, name = label.casefold(), name.casefold()
    return label == name or label.endswith(" " + name)


def parse_game(event: dict) -> dict | None:
    """The SyncedGame fields for a head-to-head game event, or None if it isn't one."""
    if (event.get("product_metadata") or {}).get("competition_scope") != "Game":
        return None
    if not event.get("mutually_exclusive"):
        return None
    markets = event.get("markets") or []
    ties = [m for m in markets if m["ticker"].endswith("-TIE")]
    sides = [m for m in markets if not m["ticker"].endswith("-TIE")]
    if len(sides) != 2 or len(ties) > 1:
        return None  # races, tournaments, and other many-way events

    a, b = sides
    title = event.get("title") or event["event_ticker"]
    # drop prefixes like "eSoccer: " or "Game 7: " before matching the first name
    first = title.split(" vs ")[0].rsplit(": ", 1)[-1].strip()
    if not _names(market_label(a), first) and _names(market_label(b), first):
        a, b = b, a  # put the sides in title order
    return {
        "series_ticker": event.get("series_ticker") or series_of(event["event_ticker"]),
        "league": ((event.get("product_metadata") or {}).get("competition") or "Other")[:100],
        "title": title[:500],
        "team_a_ticker": a["ticker"],
        "team_b_ticker": b["ticker"],
        "tie_ticker": ties[0]["ticker"] if ties else "",
        "volume_24h": sum(to_contracts(m.get("volume_24h_fp")) for m in markets),
    }


def upsert_games(db: Session, games: dict[str, dict], *, complete: bool) -> int:
    """Store games keyed by event ticker. When `complete` is true (we read the whole
    schedule), games we didn't see this time are finished or cancelled, so drop them."""
    now = datetime.now(UTC)
    existing = {g.event_ticker: g for g in db.scalars(select(SyncedGame))}  # a few thousand
    for ticker, fields in games.items():
        row = existing.get(ticker)
        if row is None:
            row = SyncedGame(event_ticker=ticker)
            db.add(row)
        for field, value in fields.items():
            setattr(row, field, value)
        row.synced_at = now
    db.flush()
    if complete:
        db.execute(
            delete(SyncedGame).where(SyncedGame.synced_at < now),
            execution_options={"synchronize_session": False},  # committed just below
        )
    db.commit()
    return len(games)
