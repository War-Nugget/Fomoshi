import asyncio

import httpx

from app.kalshi.client import LiveKalshiClient, get_kalshi
from app.main import app
from app.worker import settle_and_snapshot
from tests.conftest import find_market, set_book

TICKER = "KXSAMPLECPI-01-ABOVE"


def order(client, auth, side="yes", qty=10, action="buy", **extra):
    return client.post(
        "/api/trades",
        headers=auth,
        json={"ticker": TICKER, "side": side, "action": action, "quantity": qty, **extra},
    )


def test_trading_requires_login(client):
    assert order(client, {}).status_code == 401


def test_market_detail_and_orderbook(client):
    detail = client.get(f"/api/markets/{TICKER}").json()
    assert detail["event_title"].startswith("Sample:")
    assert detail["series_ticker"] == "KXSAMPLECPI"
    book = client.get(f"/api/markets/{TICKER}/orderbook").json()
    assert book["yes_asks"][0]["price"] == round(1 - book["no_bids"][0]["price"], 6)
    assert client.get("/api/markets/NOPE").status_code == 404


def test_preview_matches_execution(client, auth, kalshi):
    set_book(kalshi, TICKER, yes=[(0.30, 100)], no=[(0.65, 5), (0.64, 100)])
    body = {"ticker": TICKER, "side": "yes", "action": "buy", "quantity": 10}
    preview = client.post("/api/trades/preview", json=body).json()
    assert preview["fills"] == [{"price": 0.35, "quantity": 5}, {"price": 0.36, "quantity": 5}]
    assert preview["total"] == 3.55 and preview["max_payout"] == 10

    result = order(client, auth).json()
    assert result["trade"]["total"] == preview["total"]
    assert result["cash"] == 1000 - 3.55


def test_buy_then_sell_realizes_pnl(client, auth, kalshi):
    set_book(kalshi, TICKER, yes=[(0.30, 100)], no=[(0.60, 100)])
    order(client, auth, qty=20)  # 20 @ $0.40 = $8.00
    set_book(kalshi, TICKER, yes=[(0.55, 100)], no=[(0.40, 100)])  # price moved up
    r = order(client, auth, action="sell", qty=10)
    assert r.status_code == 201
    assert r.json()["trade"]["realized_pnl"] == 1.5  # 10 * (0.55 - 0.40)

    pf = client.get("/api/portfolio", headers=auth).json()
    pos = pf["positions"][0]
    assert pos["quantity"] == 10 and pos["avg_cost"] == 0.40 and pos["realized_pnl"] == 1.5
    assert pf["equity"] == round(pf["cash"] + pf["positions_value"], 6)

    history = client.get("/api/trades", headers=auth).json()
    assert [t["action"] for t in history] == ["sell", "buy"]
    assert history[0]["market_title"] == "Above 0.3%"


def test_cannot_oversell_or_overspend(client, auth, kalshi):
    assert order(client, auth, action="sell", qty=1).json()["detail"].startswith("You only hold 0")
    set_book(kalshi, TICKER, yes=[], no=[(0.01, 1_000_000)])  # YES offered at $0.99
    r = order(client, auth, qty=5_000)  # would cost $4,950
    assert r.status_code == 400 and "Not enough cash" in r.json()["detail"]
    assert client.get("/api/auth/me", headers=auth).json()["cash"] == 1000  # rolled back


def test_no_liquidity_and_limits(client, auth, kalshi):
    set_book(kalshi, TICKER, yes=[(0.30, 100)], no=[(0.60, 100)])
    r = order(client, auth, limit_price=0.35)  # best YES ask is 0.40
    assert r.status_code == 400 and "No liquidity" in r.json()["detail"]


def test_orders_fill_against_a_fresh_book(client, auth, kalshi):
    """Previews may read a cached book; orders must see Kalshi's book as it is now."""
    market = dict(find_market(kalshi, TICKER))
    book = {"yes_dollars": [["0.3000", "100.00"]], "no_dollars": [["0.6000", "100.00"]]}

    def kalshi_api(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/orderbook"):
            return httpx.Response(200, json={"orderbook_fp": book})
        return httpx.Response(200, json={"market": market})

    live = LiveKalshiClient("https://kalshi.test")
    live._http = httpx.AsyncClient(
        base_url="https://kalshi.test", transport=httpx.MockTransport(kalshi_api)
    )
    app.dependency_overrides[get_kalshi] = lambda: live
    body = {"ticker": TICKER, "side": "yes", "action": "buy", "quantity": 10}

    assert client.post("/api/trades/preview", json=body).json()["avg_price"] == 0.40  # now cached
    book["no_dollars"] = [["0.4500", "100.00"]]  # a score: YES jumps to 55¢ on Kalshi
    assert client.post("/api/trades/preview", json=body).json()["avg_price"] == 0.40  # stale

    result = order(client, auth).json()
    assert result["trade"]["avg_price"] == 0.55  # not the stale 40¢
    # the fresh read also refreshed the cache, so previews catch up too
    assert client.post("/api/trades/preview", json=body).json()["avg_price"] == 0.55

    market["status"] = "closed"  # winner declared; the cached market still says active
    assert "not open" in order(client, auth).json()["detail"]


def test_closed_market_rejected(client, auth, kalshi):
    find_market(kalshi, TICKER)["status"] = "closed"
    assert "not open" in order(client, auth).json()["detail"]


def test_settlement_pays_winners_once(client, auth, kalshi, db):
    set_book(kalshi, TICKER, yes=[(0.30, 100)], no=[(0.60, 100)])
    order(client, auth, side="yes", qty=10)  # $4.00
    order(client, auth, side="no", qty=10)  # NO ask = 1 - 0.30 = $0.70 -> $7.00
    assert client.get("/api/auth/me", headers=auth).json()["cash"] == 989

    find_market(kalshi, TICKER).update(status="finalized", result="yes")
    assert asyncio.run(settle_and_snapshot(db, kalshi)) == 2
    assert asyncio.run(settle_and_snapshot(db, kalshi)) == 0  # idempotent

    assert client.get("/api/auth/me", headers=auth).json()["cash"] == 999  # YES pays $10
    history = client.get("/api/trades", headers=auth).json()
    settles = {t["side"]: t["realized_pnl"] for t in history if t["action"] == "settle"}
    assert settles == {"yes": 6.0, "no": -7.0}
    pf = client.get("/api/portfolio", headers=auth).json()
    assert {p["status"] for p in pf["positions"]} == {"settled"}


def test_equity_history(client, auth, kalshi, db):
    asyncio.run(settle_and_snapshot(db, kalshi))  # writes today's snapshot
    points = client.get("/api/portfolio/history", headers=auth).json()
    assert points[-1]["equity"] == 1000
