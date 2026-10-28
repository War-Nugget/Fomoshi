import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
from app.kalshi.client import KalshiError, get_kalshi
from app.routers import auth, markets, portfolio, trades
from app.trading.engine import TradeError
from app.trading.settlement import settlement_loop

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("fomoshi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.secret_key.startswith("dev-only"):
        log.warning("Using the default SECRET_KEY. Set SECRET_KEY before deploying.")
    init_db()
    task = None
    if settings.settlement_interval_seconds > 0:
        task = asyncio.create_task(settlement_loop(settings.settlement_interval_seconds))
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await get_kalshi().aclose()


app = FastAPI(
    title="Fomoshi API",
    description="Paper-trade prediction markets using live Kalshi prices. Play money only.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(TradeError)
async def trade_error_handler(_: Request, exc: TradeError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(KalshiError)
async def kalshi_error_handler(_: Request, exc: KalshiError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "kalshi_mode": get_settings().kalshi_mode}


app.include_router(auth.router)
app.include_router(markets.router)
app.include_router(trades.router)
app.include_router(portfolio.router)
