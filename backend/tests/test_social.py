from tests.conftest import register, set_book

TICKER = "KXSAMPLECPI-01-ABOVE"


def buy(client, h, qty):
    r = client.post(
        "/api/trades",
        headers=h,
        json={"ticker": TICKER, "side": "yes", "action": "buy", "quantity": qty},
    )
    assert r.status_code == 201, r.text


def test_leaderboard_ranks_by_account_value(client, synced):
    a = register(client, "ana")
    b = register(client, "bob")
    register(client, "cyd")
    # Book with a wide spread: buying at 40c and marking at the 30c bid loses money
    set_book(synced, TICKER, yes=[(0.30, 1000)], no=[(0.60, 1000)])
    buy(client, a, 100)  # ana: pays $40, marked at the synced bid
    board = client.get("/api/leaderboard", headers=b).json()
    assert board["total_players"] == 3
    assert board["rows"][-1]["username"] == "ana" and board["rows"][-1]["gain"] < 0
    assert board["you"]["username"] == "bob" and board["you"]["is_you"]
    assert client.get("/api/leaderboard").json()["you"] is None  # signed out works too


def test_leagues(client, synced):
    a = register(client, "ana")
    b = register(client, "bob")
    league = client.post("/api/leagues", headers=a, json={"name": "Dorm 4B"}).json()
    code = league["invite_code"]
    assert len(code) == 8 and league["is_owner"] and league["member_count"] == 1

    assert (
        client.post("/api/leagues/join", headers=b, json={"invite_code": "ZZZZZZZZ"}).status_code
        == 404
    )
    joined = client.post("/api/leagues/join", headers=b, json={"invite_code": code.lower()}).json()
    assert joined["member_count"] == 2 and not joined["is_owner"]
    again = client.post("/api/leagues/join", headers=b, json={"invite_code": code}).json()
    assert again["member_count"] == 2  # joining twice is harmless

    set_book(synced, TICKER, yes=[(0.30, 1000)], no=[(0.60, 1000)])
    buy(client, b, 100)  # bo loses value vs. when he joined
    detail = client.get(f"/api/leagues/{league['id']}", headers=a).json()
    assert [r["username"] for r in detail["standings"]] == ["ana", "bob"]
    assert detail["standings"][1]["gain"] < 0 and detail["your_rank"] == 1

    outsider = register(client, "cyd")
    assert client.get(f"/api/leagues/{league['id']}", headers=outsider).status_code == 404
    assert [lg["name"] for lg in client.get("/api/leagues", headers=b).json()] == ["Dorm 4B"]

    assert client.delete(f"/api/leagues/{league['id']}/membership", headers=b).status_code == 204
    assert client.get("/api/leagues", headers=b).json() == []
    # owner leaving deletes the league
    assert client.delete(f"/api/leagues/{league['id']}/membership", headers=a).status_code == 204
    assert client.get(f"/api/leagues/{league['id']}", headers=a).status_code == 404
