from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production", "test"] = "development"

    # Market data
    kalshi_mode: Literal["live", "mock"] = "live"
    kalshi_base_url: str = "https://external-api.kalshi.com/trade-api/v2"

    # Storage
    database_url: str = "sqlite:///./fomoshi.db"
    redis_url: str | None = None  # shared cache + rate limits; in-memory when unset
    auto_migrate: bool = True  # run `alembic upgrade head` on API startup

    # Auth
    secret_key: str = DEV_SECRET
    access_token_minutes: int = 60 * 24 * 7
    password_reset_minutes: int = 60

    # Game
    starting_cash: float = 1000.0

    # Background worker
    run_worker_in_process: bool = True  # set false in production and run `python -m app.worker`
    settlement_interval_seconds: int = 60
    market_sync_interval_seconds: int = 300
    market_sync_max_pages: int = 50
    games_sync_interval_seconds: int = 300
    games_lookahead_hours: int = 72  # how far ahead the Games page lists matchups
    games_sync_max_pages: int = 30  # pages of Kalshi's sports schedule (200 per page)

    # Web
    app_url: str = "http://localhost:5173"  # used in password-reset emails
    cors_origins: str = "http://localhost:5173"
    rate_limit_enabled: bool = True

    # Email (password resets). When smtp_host is unset, emails are written to the log.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "Fomoshi <no-reply@localhost>"
    smtp_starttls: bool = True

    # Monitoring
    sentry_dsn: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _check_production(self):
        if self.environment == "production":
            if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
                raise ValueError("Set SECRET_KEY to a random value of at least 32 characters")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Use PostgreSQL (DATABASE_URL) in production")
        # Heroku/Render style URLs -> SQLAlchemy psycopg driver
        for prefix in ("postgres://", "postgresql://"):
            if self.database_url.startswith(prefix):
                self.database_url = "postgresql+psycopg://" + self.database_url[len(prefix) :]
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
