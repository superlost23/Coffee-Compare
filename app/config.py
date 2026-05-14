"""Centralized settings loaded from environment.

All env reads should go through `settings`; never read `os.environ` directly
elsewhere in the codebase. Makes it trivial to override in tests.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://coffee:coffee@db:5432/coffee_compare"

    # Meilisearch
    meili_url: str = "http://meili:7700"
    meili_master_key: str = "dev-key"

    # Anthropic
    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-4-5"

    # Admin
    admin_path_token: str = "dev-admin-token"
    admin_username: str = "admin"
    admin_password: str = "dev-password"

    # Scraping
    scrape_user_agent: str = "CoffeeCompareBot/0.1"
    scrape_request_delay_ms: int = Field(default=1000, ge=0)
    scrape_timeout_s: int = 30

    # Currency
    openexchangerates_app_id: str = ""


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()
