import asyncio

from sqlalchemy import select

from app.models import SyncedMarket
from app.worker import sync_catalog


def test_falls_back_to_live_before_first_sync(client):
    page = client.get("/api/markets").json()
    assert len(page["events"]) == 6 and page["has_more"] is False


def test_listing_from_catalog(client, synced):
    page = client.get("/api/markets", params={"page_size": 4}).json()
    assert page["total"] == 6 and len(page["events"]) == 4 and page["has_more"]
    page2 = client.get("/api/markets", params={"page_size": 4, "page": 2}).json()
    assert len(page2["events"]) == 2 and not page2["has_more"]
    seen = {e["event_ticker"] for e in page["events"] + page2["events"]}
    assert len(seen) == 6  # pages don't overlap

    vols = [e["volume_24h"] for e in page["events"]]
    assert vols == sorted(vols, reverse=True)  # trending = 24h volume


def test_search_category_and_sort(client, synced):
    hits = client.get("/api/markets", params={"q": "comets"}).json()["events"]
    assert [e["event_ticker"] for e in hits] == ["KXSAMPLECHAMP-01"]  # matched an outcome label
    hits = client.get("/api/markets", params={"q": "box office"}).json()["events"]
    assert [e["event_ticker"] for e in hits] == ["KXSAMPLEBOX-01"]  # matched the title
    assert client.get("/api/markets", params={"q": "100%_"}).json()["total"] == 0  # escaped

    ent = client.get("/api/markets", params={"category": "entertainment"}).json()
    assert ent["total"] == 2 and all(e["category"] == "Entertainment" for e in ent["events"])

    closing = client.get("/api/markets", params={"sort": "closing"}).json()["events"]
    assert closing and all(e["close_time"] for e in closing)

    cats = {c["name"]: c["count"] for c in client.get("/api/markets/categories").json()}
    assert cats["Entertainment"] == 2 and sum(cats.values()) == 6


def test_unseen_markets_are_retired(client, synced, db):
    synced.events = [e for e in synced.events if e["event_ticker"] != "KXSAMPLECPI-01"]
    asyncio.run(sync_catalog(db, synced))
    row = db.scalar(select(SyncedMarket).where(SyncedMarket.ticker == "KXSAMPLECPI-01-ABOVE"))
    db.refresh(row)
    assert row.status == "inactive"
    assert client.get("/api/markets").json()["total"] == 5


def test_event_detail(client):
    e = client.get("/api/events/KXSAMPLECHAMP-01").json()
    assert e["title"].startswith("Sample: Who will win")
    prices = [m["last_price"] for m in e["markets"]]
    assert prices == sorted(prices, reverse=True) and len(prices) == 4
    assert client.get("/api/events/NOPE").status_code == 404
