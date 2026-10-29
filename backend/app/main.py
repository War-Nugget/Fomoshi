import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import DEV_SECRET, get_settings
from app.db import SessionLocal, run_migrations
from app.kalshi.client import KalshiError, get_kalshi
from app.routers import auth, markets, portfolio, social, trades
from app.trading.engine import TradeError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("fomoshi")

settings = get_settings()

if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.1
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.secret_key == DEV_SECRET:
        log.warning("Using the default SECRET_KEY. Set SECRET_KEY before deploying.")
    if settings.auto_migrate:
        await asyncio.to_thread(run_migrations)

    stop = asyncio.Event()
    worker_task = None
    if settings.run_worker_in_process:
        from app.worker import run_forever

        log.info("running the background worker inside the API process")
        worker_task = asyncio.create_task(run_forever(stop))
    yield
    stop.set()
    if worker_task:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task
    await get_kalshi().aclose()


app = FastAPI(
    title="Fomoshi API",
    description="Paper-trade prediction markets using live Kalshi prices. Play money only.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,  # auth uses bearer tokens, not cookies
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.exception_handler(TradeError)
async def trade_error_handler(_: Request, exc: TradeError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(KalshiError)
async def kalshi_error_handler(_: Request, exc: KalshiError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/api/health", tags=["meta"])
def health():
    db_ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "kalshi_mode": settings.kalshi_mode,
        },
    )


app.include_router(auth.router)
app.include_router(markets.router)
app.include_router(trades.router)
app.include_router(portfolio.router)
app.include_router(social.router)
