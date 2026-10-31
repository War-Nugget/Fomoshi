"""Generates sample Kalshi-format fixtures for Fomoshi's mock mode.

Run from backend/:  python scripts/make_fixtures.py app/kalshi/fixtures
"""

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

random.seed(7)
out = Path(sys.argv[1])
CLOSE = "2030-12-31T23:00:00Z"

EVENTS = [
    (
        "KXSAMPLETEMP",
        "KXSAMPLETEMP-01",
        "Sample: NYC high temperature tomorrow",
        "Climate and Weather",
        [("80F", "80° or above", 0.18), ("75TO79", "75° to 79°", 0.47), ("B75", "Below 75°", 0.36)],
    ),
    (
        "KXSAMPLECPI",
        "KXSAMPLECPI-01",
        "Sample: Will monthly CPI come in above 0.3%?",
        "Economics",
        [("ABOVE", "Above 0.3%", 0.34)],
    ),
    (
        "KXSAMPLECHAMP",
        "KXSAMPLECHAMP-01",
        "Sample: Who will win the Galaxy League championship?",
        "Sports",
        [
            ("COMETS", "Atlanta Comets", 0.41),
            ("PEAKS", "Denver Peaks", 0.27),
            ("HARBORS", "Boston Harbors", 0.19),
            ("RIVALS", "Field (any other team)", 0.13),
        ],
    ),
    (
        "KXSAMPLEBOX",
        "KXSAMPLEBOX-01",
        "Sample: Opening weekend box office above $100M?",
        "Entertainment",
        [("100M", "Above $100M", 0.62)],
    ),
    (
        "KXSAMPLETECH",
        "KXSAMPLETECH-01",
        "Sample: Will a new flagship phone launch before year end?",
        "Science and Technology",
        [("YES", "Launches before year end", 0.83)],
    ),
    (
        "KXSAMPLEGAME",
        "KXSAMPLEGAME-01",
        "Sample: Top-selling video game this month",
        "Entertainment",
        [
            ("SKY", "Skyforge Odyssey", 0.52),
            ("NEON", "Neon Drift 3", 0.31),
            ("OTHER", "Any other game", 0.17),
        ],
    ),
]


def d(x: float) -> str:
    return f"{x:.4f}"


# Head-to-head games, listed the way Kalshi does: "Team A vs Team B" with one market
# per side plus a tie market where draws count. Start offsets are minutes from
# FIXTURE_NOW (2030-01-01), which the mock client moves to the current time.
FIXTURE_NOW = datetime(2030, 1, 1, tzinfo=UTC)
GAMES = [
    (
        "KXSAMPLEHOOPSGAME",
        "KXSAMPLEHOOPSGAME-01",
        "Seattle Tides vs Phoenix Flares",
        "Sample Basketball",
        -45,
        [("SEA", "Seattle Tides", 0.62), ("PHX", "Phoenix Flares", 0.38)],
    ),
    (
        "KXSAMPLESOCCERGAME",
        "KXSAMPLESOCCERGAME-01",
        "Kingsport vs Northgate",
        "Sample Soccer",
        -30,
        # listed out of title order on purpose, as Kalshi sometimes does
        [("NGT", "Northgate", 0.30), ("KIN", "Kingsport", 0.45), ("TIE", "Tie", 0.25)],
    ),
    (
        "KXSAMPLEHOOPSGAME",
        "KXSAMPLEHOOPSGAME-02",
        "Chicago Lanterns vs Austin Mesas",
        "Sample Basketball",
        180,
        [("CHI", "Chicago Lanterns", 0.55), ("AUS", "Austin Mesas", 0.45)],
    ),
    (
        "KXSAMPLESOCCERGAME",
        "KXSAMPLESOCCERGAME-02",
        "Rivertown vs Lakeside",
        "Sample Soccer",
        26 * 60,
        [("RIV", "Rivertown", 0.40), ("LAK", "Lakeside", 0.33), ("TIE", "Tie", 0.27)],
    ),
    (
        "KXSAMPLEHOOPSGAME",
        "KXSAMPLEHOOPSGAME-03",
        "Portland Pines vs Memphis Kings",
        "Sample Basketball",
        10 * 24 * 60,  # beyond the Games page horizon
        [("POR", "Portland Pines", 0.48), ("MEM", "Memphis Kings", 0.52)],
    ),
]


events, books = [], {}


def build_markets(event: str, title: str, outcomes) -> list[dict]:
    markets = []
    for suffix, label, p in outcomes:
        ticker = f"{event}-{suffix}"
        cents = round(p * 100)
        yes_bids = [(cents - i, random.randint(20, 900)) for i in range(1, 9) if cents - i >= 1]
        no_bids = [
            (100 - cents - i, random.randint(20, 900)) for i in range(1, 9) if 100 - cents - i >= 1
        ]
        books[ticker] = {
            "orderbook_fp": {
                "yes_dollars": [[d(c / 100), f"{q}.00"] for c, q in sorted(yes_bids)],
                "no_dollars": [[d(c / 100), f"{q}.00"] for c, q in sorted(no_bids)],
            }
        }
        yb, nb = max(yes_bids)[0], max(no_bids)[0]
        vol = random.randint(2_000, 400_000)
        markets.append(
            {
                "ticker": ticker,
                "event_ticker": event,
                "market_type": "binary",
                "title": title,
                "subtitle": "",
                "yes_sub_title": label,
                "no_sub_title": label,
                "status": "active",
                "result": "",
                "yes_bid_dollars": d(yb / 100),
                "yes_ask_dollars": d((100 - nb) / 100),
                "no_bid_dollars": d(nb / 100),
                "no_ask_dollars": d((100 - yb) / 100),
                "last_price_dollars": d(cents / 100),
                "previous_price_dollars": d((cents - 1) / 100),
                "volume_fp": f"{vol}.00",
                "volume_24h_fp": f"{vol // 9}.00",
                "open_interest_fp": f"{vol // 3}.00",
                "open_time": "2026-01-01T00:00:00Z",
                "close_time": CLOSE,
                "rules_primary": f'Sample market for Fomoshi\'s offline mode. Resolves YES if "{label}" happens. Not a real Kalshi market.',
            }
        )
    return markets


for series, event, title, category, outcomes in EVENTS:
    events.append(
        {
            "event_ticker": event,
            "series_ticker": series,
            "title": title,
            "sub_title": "Sample data",
            "category": category,
            "markets": build_markets(event, title, outcomes),
        }
    )

milestones = []
for series, event, title, competition, start_offset, outcomes in GAMES:
    events.append(
        {
            "event_ticker": event,
            "series_ticker": series,
            "title": title,
            "sub_title": "Sample data",
            "category": "Sports",
            "mutually_exclusive": True,
            "product_metadata": {"competition": competition, "competition_scope": "Game"},
            "markets": build_markets(event, title, outcomes),
        }
    )
    start = FIXTURE_NOW + timedelta(minutes=start_offset)
    milestones.append(
        {
            "id": f"sample-{event.lower()}",
            "category": "Sports",
            "type": "basketball_game" if "HOOPS" in series else "soccer_tournament_multi_leg",
            "title": title,
            "start_date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "details": {"main_game_event_ticker": event},
            "primary_event_tickers": [event],
            "related_event_tickers": [event],
        }
    )
# A schedule entry whose event is a season-long future, not a game: it must be ignored.
milestones.append(
    {
        "id": "sample-champ",
        "category": "Sports",
        "type": "one_off_milestone",
        "title": "Galaxy League championship",
        "start_date": FIXTURE_NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "details": {},
        "primary_event_tickers": ["KXSAMPLECHAMP-01"],
        "related_event_tickers": ["KXSAMPLECHAMP-01"],
    }
)

(out / "events.json").write_text(json.dumps({"events": events, "cursor": ""}, indent=2))
(out / "orderbooks.json").write_text(json.dumps(books, indent=2))
(out / "milestones.json").write_text(json.dumps({"milestones": milestones, "cursor": ""}, indent=2))
print(len(events), "events,", len(books), "markets,", len(milestones), "milestones")
