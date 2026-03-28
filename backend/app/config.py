"""
Centralized configuration for the Crave API.

All tunable values (model IDs, CORS, feature flags) live here so operators and
hackathon judges can adjust behavior without hunting through the codebase.
Environment variables override defaults via pydantic-settings.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    gemini_recipe_model: str = "gemini-2.5-flash"
    gemini_live_model: str = "gemini-live-2.5-flash-preview"
    crave_cors_origins: str = (
        "http://127.0.0.1:5500,http://localhost:5500,"
        "http://127.0.0.1:8080,http://localhost:8080,"
        "http://127.0.0.1:3000,http://localhost:3000"
    )
    crave_dry_run_default: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""

        return [o.strip() for o in self.crave_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton per process)."""

    return Settings()
