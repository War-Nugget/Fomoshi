import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.games import parse_game
from app.kalshi.client import LiveKalshiClient
from app.models import SyncedGame
from app.worker import sync_games
from tests.conftest import find_market


@pytest.fixture
def games(db, kalshi):
    """Populate the game schedule the way the worker does."""
    asyncio.run(sync_games(db, kalshi))
    return kalshi


def test_sync_keeps_only_games_in_the_window(games, db):
    tickers = set(db.scalars(select(SyncedGame.event_ticker)))
    # -03 starts beyond the lookahead; the championship future isn't a game
    assert tickers == {
        "KXSAMPLEHOOPSGAME-01",
        "KXSAMPLEHOOPSGAME-02",
        "KXSAMPLESOCCERGAME-01",
        "KXSAMPLESOCCERGAME-02",
    }


def test_live_games_first_then_upcoming(client, games):
    page = client.get("/api/games").json()
    assert page["total"] == 4 and not page["has_more"]
    listed = page["games"]
    assert [g["live"] for g in listed] == [True, True, False, False]
    live_volumes = [g["volume_24h"] for g in listed[:2]]
    assert live_volumes == sorted(live_volumes, reverse=True)
    upcoming = [g["start_time"] for g in listed[2:]]
    assert upcoming == sorted(upcoming)


def test_sides_follow_the_title_and_ties_are_kept(client, games):
    listed = {g["event_ticker"]: g for g in client.get("/api/games").json()["games"]}
    soccer = listed["KXSAMPLESOCCERGAME-01"]
    # Kalshi lists Northgate first, but the title (and the card) put Kingsport first
    assert soccer["title"] == "Kingsport vs Northgate"
    assert (soccer["team_a"]["label"], soccer["team_b"]["label"]) == ("Kingsport", "Northgate")
    assert soccer["tie"]["ticker"] == "KXSAMPLESOCCERGAME-01-TIE"
    assert soccer["team_a"]["yes_ask"] and soccer["team_b"]["yes_ask"]

    hoops = listed["KXSAMPLEHOOPSGAME-01"]
    assert hoops["team_a"]["label"] == "Seattle Tides" and hoops["tie"] is None
    assert hoops["league"] == "Sample Basketball"


def test_league_filter(client, games):
    leagues = {lg["name"]: lg["count"] for lg in client.get("/api/games/leagues").json()}
    assert leagues == {"Sample Basketball": 2, "Sample Soccer": 2}
    soccer = client.get("/api/games", params={"league": "sample soccer"}).json()["games"]
    assert {g["league"] for g in soccer} == {"Sample Soccer"} and len(soccer) == 2


def test_finished_games_drop_out(client, games):
    for side in ("SEA", "PHX"):
        find_market(games, f"KXSAMPLEHOOPSGAME-01-{side}")["status"] = "closed"
    tickers = [g["event_ticker"] for g in client.get("/api/games").json()["games"]]
    assert "KXSAMPLEHOOPSGAME-01" not in tickers and len(tickers) == 3


def test_resync_drops_games_no_longer_scheduled(games, db):
    games.milestones = [
        m
        for m in games.milestones
        if m["details"].get("main_game_event_ticker") != "KXSAMPLEHOOPSGAME-02"
    ]
    asyncio.run(sync_games(db, games))
    assert db.get(SyncedGame, "KXSAMPLEHOOPSGAME-02") is None
    assert db.get(SyncedGame, "KXSAMPLEHOOPSGAME-01") is not None


def test_schedule_reads_wait_out_rate_limits(monkeypatch):
    """A 429 partway through a sync's ~180 requests waits and retries, not aborts."""
    responses = iter(
        [
            httpx.Response(200, json={"milestones": [{"id": "1"}], "cursor": "next"}),
            httpx.Response(429),
            httpx.Response(200, json={"milestones": [{"id": "2"}], "cursor": ""}),
        ]
    )
    live = LiveKalshiClient("https://kalshi.test")
    live._http = httpx.AsyncClient(
        base_url="https://kalshi.test", transport=httpx.MockTransport(lambda _: next(responses))
    )
    waits = []

    async def no_wait(seconds):
        waits.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    milestones = asyncio.run(live.get_milestones(datetime.now(UTC)))
    assert [m["id"] for m in milestones] == ["1", "2"] and 1 in waits


def test_empty_before_first_sync(client):
    assert client.get("/api/games").json() == {
        "games": [],
        "total": 0,
        "page": 1,
        "page_size": 24,
        "has_more": False,
    }


def _event(title, labels, **extra):
    return {
        "event_ticker": "KXTEST-1",
        "series_ticker": "KXTEST",
        "title": title,
        "mutually_exclusive": True,
        "product_metadata": {"competition": "ITF", "competition_scope": "Game"},
        "markets": [
            {"ticker": f"KXTEST-1-{i}", "yes_sub_title": lbl} for i, lbl in enumerate(labels)
        ],
        **extra,
    }


def test_title_order_matches_surnames():
    # A real tennis listing: surnames in the title, full names on the markets
    game = parse_game(_event("Tudorica vs Colin", ["Paul Colin", "Alvin Nicholas Tudorica"]))
    assert (game["team_a_ticker"], game["team_b_ticker"]) == ("KXTEST-1-1", "KXTEST-1-0")


def test_title_order_ignores_prefixes():
    title = "eBasketball: Los Angeles Lakers (Bryce) vs New York Knicks (Cade)"
    game = parse_game(_event(title, ["New York Knicks (Cade)", "Los Angeles Lakers (Bryce)"]))
    assert game["team_a_ticker"] == "KXTEST-1-1"


def test_only_head_to_head_game_events_count():
    assert parse_game(_event("A vs B", ["A", "B"])) is not None
    assert parse_game(_event("A vs B", ["A", "B"], product_metadata={})) is None
    assert parse_game(_event("A vs B", ["A", "B"], mutually_exclusive=False)) is None
    assert parse_game(_event("Race winner", ["A", "B", "C", "D"])) is None
