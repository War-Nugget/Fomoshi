import os
import tempfile
from pathlib import Path

# Configure before the app (and its DB engine) is imported.
_tmp = Path(tempfile.mkdtemp())
os.environ.update(
    KALSHI_MODE="mock",
    DATABASE_URL=f"sqlite:///{_tmp / 'test.db'}",
    SETTLEMENT_INTERVAL_SECONDS="0",
    STARTING_CASH="1000",
    SECRET_KEY="test-secret-key-that-is-long-enough-for-hs256",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.kalshi.client import MockKalshiClient, get_kalshi  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def kalshi():
    return MockKalshiClient()


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(db, kalshi):
    app.dependency_overrides[get_kalshi] = lambda: kalshi
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    r = client.post("/api/auth/register", json={"username": "sahil", "password": "hunter2hunter2"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def set_book(kalshi: MockKalshiClient, ticker: str, yes: list, no: list) -> None:
    """Replace a market's order book with simple [(price, qty)] levels."""
    kalshi.orderbooks[ticker] = {
        "orderbook_fp": {
            "yes_dollars": [[f"{p:.4f}", f"{q}.00"] for p, q in sorted(yes)],
            "no_dollars": [[f"{p:.4f}", f"{q}.00"] for p, q in sorted(no)],
        }
    }
