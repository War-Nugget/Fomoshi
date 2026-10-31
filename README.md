# Fomoshi

Paper-trade prediction markets with live prices and play money.

Fomoshi mirrors every open market on [Kalshi](https://kalshi.com) through its public API. Each account starts with $1,000 of fake money to trade YES or NO. Orders fill against Kalshi's live order book, positions pay out automatically when markets settle, and you can compete on a global leaderboard or in private leagues with friends.

![Event page with a multi-outcome probability chart](docs/event.png)

| Market and trade ticket | Portfolio |
|---|---|
| ![Market page](docs/market.png) | ![Portfolio](docs/portfolio.png) |
| **Leaderboard and leagues** | **Mobile** |
| ![Leaderboard](docs/leaderboard.png) | ![Mobile](docs/mobile.png) |

## Features

- **Every open Kalshi market**, synced into the database every 5 minutes, with search, category filters, sorting (trending, most traded, closing soon, newest), and pagination
- **Probability charts** (1D / 1W / 1M / All) from Kalshi's candlestick data, including multi-line charts for events with several outcomes
- **Games page**: live and upcoming head-to-head matchups (Team A vs Team B, plus a tie where draws count) from Kalshi's sports schedule, with a live badge and prices refreshing every 3 seconds
- **Realistic fills**: orders walk the live order book level by level, with optional limit prices, and always read Kalshi's book fresh at trade time (never from cache), so in-game prices can't be sniped
- **Automatic settlement**: winning contracts pay $1 when Kalshi decides a market
- **Portfolio**: live P&L, settled positions, full trade history, and a daily account-value chart
- **Leaderboard and private leagues** with invite codes, ranked by gain since joining
- **Accounts**: sign up with email, password reset by email, change password (signs out other devices), delete account
- Landing page, how-it-works, terms and privacy pages, dark mode, mobile layout

## How the trading works

A contract pays **$1** if its side wins and **$0** if it loses, so a 41¢ YES price means about a 41% chance.

Kalshi publishes only **bids**. Because YES + NO always pays $1, a NO bid at 58¢ is the same as a YES offer at 42¢, so Fomoshi derives the asks from the opposite side's bids:

```
best YES ask = $1 − best NO bid
best NO ask  = $1 − best YES bid
```

Buys take the cheapest asks first; sells hit the highest bids. Orders are immediate-or-cancel. See [`backend/app/trading/orderbook.py`](backend/app/trading/orderbook.py).

Money is stored as integer **micros** (millionths of a dollar), never floats.

## Architecture

```
            ┌──────────── browser ────────────┐
            │  React + TypeScript (Vite)      │
            └───────────────┬─────────────────┘
                            │ /api
┌───────────────────────────▼─────────────────────────────┐
│ FastAPI                                                  │
│  auth · markets · trades · portfolio · leaderboard       │──── Kalshi public API
│  row-locked trades (SELECT … FOR UPDATE)                 │     (cached in Redis)
└───────────┬───────────────────────────────┬─────────────┘
            │                               │
     ┌──────▼──────┐                 ┌──────▼──────┐
     │ PostgreSQL  │◄────────────────│   Worker    │──── Kalshi
     │ (Alembic)   │                 │ catalog sync│
     └─────────────┘                 │ settlement  │
                                     │ snapshots   │
     ┌─────────────┐                 └─────────────┘
     │    Redis    │  shared cache + rate limits
     └─────────────┘
```

**Correctness under load**
- Every trade locks the user's row before checking cash, so parallel orders can't overspend.
- Settlement locks users and then positions and re-reads them under the lock, so a position is paid exactly once.
- The worker holds a Postgres advisory lock, so only one copy runs even if you start several (the others wait as standbys).
- Migrations take their own advisory lock, so several API processes can start at once safely.
- `tests/test_concurrency.py` fires 8 simultaneous orders and 6 simultaneous settlements at real Postgres to prove it.

**Security**
- bcrypt password hashes; JWTs carry a per-user version that's bumped on password change or reset, which revokes old sessions
- Reset tokens are random, stored only as SHA-256 hashes, single-use, and expire after 60 minutes; the forgot-password response never reveals whether an email exists
- IP rate limits on sign-up, login, password reset, trading, and leagues (shared through Redis)
- Production refuses to start with a weak `SECRET_KEY` or with SQLite
- Security headers on the API and the nginx frontend; CORS limited to your domain

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 19, TypeScript, Vite, React Router, TradingView Lightweight Charts |
| Backend | FastAPI, SQLAlchemy 2, Pydantic, Alembic |
| Data | PostgreSQL 16, Redis 7 |
| Ops | Docker, docker compose, nginx, Render Blueprint, GitHub Actions, Sentry (optional) |

## Run it locally

**Quickest: everything in Docker**

```bash
cp .env.example .env      # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
```

Open http://localhost:8080. Set `KALSHI_MODE=mock` in `.env` to use built-in sample markets.

**For development**

```bash
# backend (SQLite, worker runs inside the API)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload        # API docs at http://localhost:8000/api/docs

# frontend, in a second terminal
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Password-reset emails are printed in the API log until you configure SMTP.

**Tests**

```bash
cd backend
pytest                                                    # SQLite
TEST_DATABASE_URL=postgresql://user:pass@localhost/fomoshi_test \
TEST_REDIS_URL=redis://localhost:6379/0 pytest            # Postgres + Redis + race tests
```

## Deploying

See [DEPLOY.md](DEPLOY.md): a one-click Render Blueprint (free tier) or any server with Docker.

## Project layout

```
backend/
  app/
    main.py                 FastAPI app, middleware, startup (migrations + in-process worker)
    worker.py               catalog sync, settlement, equity snapshots (python -m app.worker)
    catalog.py              local copy of Kalshi's markets
    history.py              candlesticks -> chart points
    kalshi/client.py        Kalshi API client (live + mock) with Redis/memory cache
    trading/                order book fills, trade engine, settlement, valuation
    routers/                auth, markets & events, trades, portfolio, leaderboard & leagues
    cache.py ratelimit.py emailer.py auth.py models.py schemas.py config.py db.py
  migrations/               Alembic
  tests/                    pytest (36 tests)
frontend/
  src/pages/                Landing, Markets, Event, Market, Portfolio, Leaderboard, League,
                            Login, password reset, Account, legal pages
  src/components/           PriceChart, ChanceBar, EventBlock, Layout
  nginx.conf.template       production web server config
docker-compose.yml  render.yaml  DEPLOY.md
```

## Known simplifications

- Simulated orders don't consume Kalshi's book, so two users can take the same liquidity.
- Kalshi's trading fees aren't simulated.
- Positions are valued at the best bid (falling back to the last price), which is conservative in thin markets.
- Limit orders don't rest on the book; they fill immediately or not at all.

## Disclaimer

Fomoshi is a simulator. Play money only: no deposits, withdrawals, or prizes. Market data comes from Kalshi's public API; Fomoshi is not affiliated with or endorsed by Kalshi.
