"""Background worker: syncs Kalshi's market catalog and game schedule, settles
positions, and records daily account values.

Production:  python -m app.worker      (run exactly one; extras wait on a lock)
Development: runs inside the API process when RUN_WORKER_IN_PROCESS=true.
"""

import asyncio
import logging
import signal
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.catalog import parse_time, upsert_events, upsert_markets
from app.config import get_settings
from app.db import SessionLocal, engine, is_postgres
from app.games import (
    GAME_LOOKBACK,
    milestone_event_tickers,
    parse_game,
    series_of,
    upsert_games,
)
from app.kalshi.client import KalshiClient, KalshiError, get_kalshi
from app.models import EquitySnapshot
from app.trading.settlement import open_position_tickers, settle_markets
from app.trading.valuation import equity_by_user

log = logging.getLogger("fomoshi.worker")
WORKER_LOCK_ID = 7_210_431  # arbitrary constant for pg_advisory_lock


async def sync_catalog(db: Session, kalshi: KalshiClient) -> int:
    """Copy every open Kalshi event and market into the database."""
    max_pages = get_settings().market_sync_max_pages
    started = time.monotonic()
    events = await kalshi.get_all_open_events(max_pages=max_pages)
    # If we hit the page cap we didn't see everything, so don't retire unseen markets.
    complete = len(events) < max_pages * 200
    count = upsert_events(db, events, complete=complete)
    log.info(
        "catalog sync: %d events, %d markets in %.1fs",
        len(events),
        count,
        time.monotonic() - started,
    )
    return count


async def sync_games(db: Session, kalshi: KalshiClient) -> int:
    """Find live and upcoming head-to-head games through Kalshi's sports schedule."""
    settings = get_settings()
    started = time.monotonic()
    now = datetime.now(UTC)
    horizon = now + timedelta(hours=settings.games_lookahead_hours)
    max_pages = settings.games_sync_max_pages
    milestones = await kalshi.get_milestones(now - GAME_LOOKBACK, max_pages=max_pages)

    starts: dict[str, datetime] = {}
    for m in milestones:
        start = parse_time(m.get("start_date"))
        if start is None or start > horizon:
            continue
        for ticker in milestone_event_tickers(m):
            starts.setdefault(ticker, start)

    games: dict[str, dict] = {}
    for series in sorted({series_of(t) for t in starts}):
        for event in await kalshi.get_all_open_events(max_pages=5, series_ticker=series):
            ticker = event["event_ticker"]
            if ticker in starts and (game := parse_game(event)):
                games[ticker] = {**game, "start_time": starts[ticker]}
        await asyncio.sleep(0.25)  # ~150 series per sync; stay under Kalshi's rate limit

    count = upsert_games(db, games, complete=len(milestones) < max_pages * 200)
    log.info(
        "games sync: %d games from %d schedule entries in %.1fs",
        count,
        len(milestones),
        time.monotonic() - started,
    )
    return count


async def settle_and_snapshot(db: Session, kalshi: KalshiClient) -> int:
    """Refresh every market someone holds, pay out settled ones, record equity."""
    tickers = open_position_tickers(db)
    settled = 0
    if tickers:
        markets = await kalshi.get_markets(tickers)
        upsert_markets(db, markets)
        db.commit()
        settled = settle_markets(db, markets)
    snapshot_equity(db)
    return settled


def snapshot_equity(db: Session) -> None:
    today = datetime.now(UTC).date()
    values = equity_by_user(db)
    existing = {
        s.user_id: s for s in db.scalars(select(EquitySnapshot).where(EquitySnapshot.day == today))
    }
    for user_id, equity in values.items():
        snap = existing.get(user_id)
        if snap is None:
            db.add(EquitySnapshot(user_id=user_id, day=today, equity_micros=equity))
        else:
            snap.equity_micros = equity
    db.commit()


async def _acquire_lock(stop: asyncio.Event):
    """On Postgres, only one worker loop may run across every process and server.
    Others wait here as hot standbys. Returns the connection holding the lock."""
    if not is_postgres():
        return None
    conn = engine.connect()
    while not stop.is_set():
        lock_sql = text("SELECT pg_try_advisory_lock(:id)")
        got = conn.execute(lock_sql, {"id": WORKER_LOCK_ID}).scalar()
        conn.commit()
        if got:
            return conn
        log.info("another worker holds the lock; standing by")
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            pass
    conn.close()
    return None


async def run_forever(stop: asyncio.Event | None = None) -> None:
    settings = get_settings()
    stop = stop or asyncio.Event()
    lock_conn = await _acquire_lock(stop)
    if stop.is_set():
        return
    kalshi = get_kalshi()
    last_sync = last_games_sync = 0.0
    log.info("worker loop started")
    try:
        while not stop.is_set():
            # Games first: unlike the markets page, the Games page has no live fallback.
            # Its own try, so a schedule problem never holds up settlement.
            try:
                if time.monotonic() - last_games_sync >= settings.games_sync_interval_seconds:
                    with SessionLocal() as db:
                        await sync_games(db, kalshi)
                    last_games_sync = time.monotonic()
            except KalshiError as exc:
                log.warning("Kalshi unavailable for games sync, retrying next cycle: %s", exc)
            except Exception:
                log.exception("games sync failed")
            try:
                with SessionLocal() as db:
                    if time.monotonic() - last_sync >= settings.market_sync_interval_seconds:
                        await sync_catalog(db, kalshi)
                        last_sync = time.monotonic()
                    await settle_and_snapshot(db, kalshi)
            except KalshiError as exc:
                log.warning("Kalshi unavailable, retrying next cycle: %s", exc)
            except Exception:
                log.exception("worker cycle failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.settlement_interval_seconds)
            except TimeoutError:
                pass
    finally:
        if lock_conn is not None:
            lock_conn.close()


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = get_settings()
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass

    try:
        await run_forever(stop)
    finally:
        await get_kalshi().aclose()
        log.info("worker stopped")


if __name__ == "__main__":
    asyncio.run(_main())
