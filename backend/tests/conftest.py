import asyncio
import os
import tempfile
from pathlib import Path

# Configure before the app (and its DB engine) is imported.
# Set TEST_DATABASE_URL=postgresql://... to run the whole suite against Postgres.
_tmp = Path(tempfile.mkdtemp())
os.environ.update(
    ENVIRONMENT="test",
    KALSHI_MODE="mock",
    DATABASE_URL=os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp / 'test.db'}"),
    AUTO_MIGRATE="false",
    RUN_WORKER_IN_PROCESS="false",
    STARTING_CASH="1000",
    SECRET_KEY="test-secret-key-that-is-long-enough-for-hs256",
    REDIS_URL=os.environ.get("TEST_REDIS_URL", ""),
)
if not os.environ["REDIS_URL"]:
    del os.environ["REDIS_URL"]

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.cache import get_cache  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.kalshi.client import MockKalshiClient, get_kalshi  # noqa: E402
from app.main import app  # noqa: E402
from app.worker import sync_catalog  # noqa: E402


@pytest.fixture
def kalshi():
    return MockKalshiClient()


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    asyncio.run(get_cache().clear())
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(db, kalshi):
    app.dependency_overrides[get_kalshi] = lambda: kalshi
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, username="sahil", password="hunter2hunter2", email=None) -> dict:
    r = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "email": email or f"{username}@x.io"},
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


@pytest.fixture
def synced(db, kalshi):
    """Populate the market catalog the way the worker does."""
    asyncio.run(sync_catalog(db, kalshi))
    return kalshi


def set_book(kalshi: MockKalshiClient, ticker: str, yes: list, no: list) -> None:
    """Replace a market's order book with simple [(price, qty)] levels."""
    kalshi.orderbooks[ticker] = {
        "orderbook_fp": {
            "yes_dollars": [[f"{p:.4f}", f"{q}.00"] for p, q in sorted(yes)],
            "no_dollars": [[f"{p:.4f}", f"{q}.00"] for p, q in sorted(no)],
        }
    }


def find_market(kalshi: MockKalshiClient, ticker: str) -> dict:
    return kalshi._all_markets()[ticker]
