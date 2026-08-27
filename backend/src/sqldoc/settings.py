"""Process-level settings (env vars / .env), distinct from sqldoc.yaml."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SQLDOC_", env_file=".env", extra="ignore")

    config: Path = Path("sqldoc.yaml")
    db: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8000
