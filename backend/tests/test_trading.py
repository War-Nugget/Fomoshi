import asyncio

from app.trading.settlement import run_settlement_once
from tests.conftest import set_book

TICKER = "KXSAMPLECPI-01-ABOVE"


def buy(client, auth, side="yes", qty=10, action="buy", **extra):
    return client.post(
        "/api/trades",
        headers=auth,
        json={"ticker": TICKER, "side": side, "action": action, "quantity": qty, **extra},
    )


def test_register_login_me(client):
    r = client.post("/api/auth/register", json={"username": "ana", "password": "password123"})
    assert r.status_code == 201
    assert (
        client.post(
            "/api/auth/register", json={"username": "ANA", "password": "password123"}
        ).status_code
        == 409
    )
    r = client.post("/api/auth/login", data={"username": "ana", "password": "password123"})
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["username"] == "ana" and me["cash"] == 1000
    assert (
        client.post(
            "/api/auth/login", data={"username": "ana", "password": "wrong-password"}
        ).status_code
        == 401
    )


def test_trading_requires_login(client):
    assert buy(client, {}).status_code == 401


def test_markets_list_and_detail(client):
    events = client.get("/api/markets").json()["events"]
    assert len(events) >= 5
    sports = client.get("/api/markets", params={"category": "sports"}).json()["events"]
    assert all(e["category"] == "Sports" for e in sports) and sports
    found = client.get("/api/markets", params={"q": "comets"}).json()["events"]
    assert [e["event_ticker"] for e in found] == ["KXSAMPLECHAMP-01"]

    detail = client.get(f"/api/markets/{TICKER}").json()
    assert detail["event_title"].startswith("Sample:")
    book = client.get(f"/api/markets/{TICKER}/orderbook").json()
    assert book["yes_asks"][0]["price"] == round(1 - book["no_bids"][0]["price"], 6)
    assert client.get("/api/markets/NOPE").status_code == 404


def test_preview_matches_execution(client, auth, kalshi):
    set_book(kalshi, TICKER, yes=[(0.30, 100)], no=[(0.65, 5), (0.64, 100)])
    body = {"ticker": TICKER, "side": "yes", "action": "buy", "quantity": 10}
    preview = client.post("/api/trades/preview", json=body).json()
    assert preview["fills"] == [{"price": 0.35, "quantity": 5}, {"price": 0.36, "quantity": 5}]
    assert preview["total"] == 3.55 and preview["max_payout"] == 10

    result = buy(client, auth).json()
    assert result["trade"]["total"] == preview["total"]
    assert result["cash"] == 1000 - 3.55


def test_buy_then_sell_realizes_pnl(client, auth, kalshi):
    set_book(kalshi, TICKER, yes=[(0.30, 100)], no=[(0.60, 100)])
    buy(client, auth, qty=20)  # 20 @ $0.40 = $8.00
    set_book(kalshi, TICKER, yes=[(0.55, 100)], no=[(0.40, 100)])  # price moved up
    r = buy(client, auth, action="sell", qty=10)
    assert r.status_code == 201
    assert r.json()["trade"]["realized_pnl"] == 1.5  # 10 * (0.55 - 0.40)

    pf = client.get("/api/portfolio", headers=auth).json()
    pos = pf["positions"][0]
    assert pos["quantity"] == 10 and pos["avg_cost"] == 0.40 and pos["realized_pnl"] == 1.5
    # mock market quotes its own yes_bid, so equity = cash + 10 * that bid
    assert pf["equity"] == round(pf["cash"] + pf["positions_value"], 6)


def test_cannot_oversell_or_overspend(client, auth, kalshi):
    assert buy(client, auth, action="sell", qty=1).json()["detail"].startswith("You only hold 0")
    set_book(kalshi, TICKER, yes=[], no=[(0.01, 1_000_000)])  # YES offered at $0.99
    r = buy(client, auth, qty=5_000)  # would cost $4,950
    assert r.status_code == 400 and "Not enough cash" in r.json()["detail"]


def test_no_liquidity_and_limits(client, auth, kalshi):
    set_book(kalshi, TICKER, yes=[(0.30, 100)], no=[(0.60, 100)])
    r = buy(client, auth, limit_price=0.35)  # best YES ask is 0.40
    assert r.status_code == 400 and "No liquidity" in r.json()["detail"]


def test_closed_market_rejected(client, auth, kalshi):
    kalshi.events[1]["markets"][0]["status"] = "closed"
    assert "not open" in buy(client, auth).json()["detail"]


def test_settlement_pays_winners_once(client, auth, kalshi, db):
    set_book(kalshi, TICKER, yes=[(0.30, 100)], no=[(0.60, 100)])
    buy(client, auth, side="yes", qty=10)  # $4.00
    buy(client, auth, side="no", qty=10)  # NO ask = 1 - 0.30 = $0.70 -> $7.00
    cash_before = client.get("/api/auth/me", headers=auth).json()["cash"]
    assert cash_before == 989

    market = kalshi.events[1]["markets"][0]
    market.update(status="finalized", result="yes")
    assert asyncio.run(run_settlement_once(db, kalshi)) == 2
    assert asyncio.run(run_settlement_once(db, kalshi)) == 0  # idempotent

    me = client.get("/api/auth/me", headers=auth).json()
    assert me["cash"] == 999  # YES pays $10, NO pays $0
    history = client.get("/api/trades", headers=auth).json()
    settles = {t["side"]: t["realized_pnl"] for t in history if t["action"] == "settle"}
    assert settles == {"yes": 6.0, "no": -7.0}
