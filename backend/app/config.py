from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kalshi_mode: Literal["live", "mock"] = "live"
    kalshi_base_url: str = "https://external-api.kalshi.com/trade-api/v2"

    database_url: str = "sqlite:///./fomoshi.db"

    secret_key: str = "dev-only-insecure-key-change-me"
    access_token_minutes: int = 60 * 24 * 7

    starting_cash: float = 1000.0
    settlement_interval_seconds: int = 60
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
