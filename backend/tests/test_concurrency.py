"""Race-condition tests. These need real row locks, so they only run on PostgreSQL:
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/fomoshi_test pytest"""

import threading

import pytest

from app.db import SessionLocal, is_postgres
from app.models import Position, Trade, User
from app.money import MICROS
from app.trading.engine import TradeError, execute_trade
from app.trading.orderbook import parse_orderbook
from app.trading.settlement import settle_markets

pytestmark = pytest.mark.skipif(not is_postgres(), reason="needs PostgreSQL row locks")

MARKET = {"ticker": "RACE-1", "status": "active", "close_time": None, "yes_sub_title": "Race"}
BOOK = parse_orderbook({"orderbook_fp": {"yes_dollars": [], "no_dollars": [["0.5000", "1000000"]]}})


def run_parallel(n, fn):
    barrier = threading.Barrier(n)
    results = []

    def worker():
        barrier.wait()
        results.append(fn())

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_parallel_orders_cannot_overspend(db):
    user = User(username="racer", email="r@x.io", password_hash="x", cash_micros=100 * MICROS)
    db.add(user)
    db.commit()

    def place():
        with SessionLocal() as s:
            u = s.get(User, user.id)
            try:  # each order costs $60 of the $100 balance
                execute_trade(s, u, MARKET, BOOK, side="yes", action="buy", quantity=120)
                return "filled"
            except TradeError:
                return "rejected"

    results = run_parallel(8, place)
    assert results.count("filled") == 1 and results.count("rejected") == 7
    db.expire_all()
    assert db.get(User, user.id).cash_micros == 40 * MICROS


def test_parallel_settlement_pays_once(db):
    user = User(username="holder", email="h@x.io", password_hash="x", cash_micros=0)
    db.add(user)
    db.flush()
    db.add(
        Position(user_id=user.id, ticker="RACE-1", side="yes", quantity=10, cost_micros=5 * MICROS)
    )
    db.commit()
    settled = {**MARKET, "status": "finalized", "result": "yes"}

    def settle():
        with SessionLocal() as s:
            return settle_markets(s, [settled])

    assert sum(run_parallel(6, settle)) == 1
    db.expire_all()
    assert db.get(User, user.id).cash_micros == 10 * MICROS
    assert db.query(Trade).filter_by(action="settle").count() == 1
