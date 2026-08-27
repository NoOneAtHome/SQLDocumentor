"""Pydantic models for sqldoc.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator

from sqldoc.config.errors import ConfigError

AuthMode = Literal["sql", "integrated"]
DriverName = Literal["auto", "pyodbc", "pymssql"]


class AuthCfg(BaseModel):
    mode: AuthMode = "sql"
    username: str | None = None
    password: SecretStr | None = None

    @model_validator(mode="after")
    def _require_credentials_for_sql_auth(self) -> AuthCfg:
        if self.mode == "sql":
            if not self.username:
                raise ValueError("auth.username is required when auth.mode is 'sql'")
            if self.password is None:
                raise ValueError("auth.password is required when auth.mode is 'sql'")
        return self


class DatabaseCfg(BaseModel):
    name: str
    schemas: list[str] = Field(min_length=1)


class ConnectionCfg(BaseModel):
    name: str
    host: str
    port: int = 1433
    auth: AuthCfg
    driver: DriverName = "auto"
    encrypt: bool = True
    trust_server_certificate: bool = False
    connect_timeout_seconds: int = 15
    query_timeout_seconds: int = 300
    databases: list[DatabaseCfg] = Field(min_length=1)

    def database(self, name: str) -> DatabaseCfg | None:
        wanted = name.casefold()
        for db in self.databases:
            if db.name.casefold() == wanted:
                return db
        return None

    def is_configured_database(self, name: str) -> bool:
        return self.database(name) is not None

    def is_selected(self, database: str, schema: str) -> bool:
        db = self.database(database)
        if db is None:
            return False
        wanted = schema.casefold()
        return any(s.casefold() == wanted for s in db.schemas)


class ScanOptions(BaseModel):
    cascade_foreign_keys: bool = True
    include_triggers_of_cascaded_tables: bool = True
    collect_stats: bool = True
    parse_lineage: bool = True


class StorageCfg(BaseModel):
    sqlite_path: Path = Path("sqldoc.sqlite")


class AppConfig(BaseModel):
    version: int = 1
    storage: StorageCfg = Field(default_factory=StorageCfg)
    connections: list[ConnectionCfg] = Field(min_length=1)
    scan: ScanOptions = Field(default_factory=ScanOptions)

    @model_validator(mode="after")
    def _unique_connection_names(self) -> AppConfig:
        seen: set[str] = set()
        for conn in self.connections:
            key = conn.name.casefold()
            if key in seen:
                raise ValueError(f"duplicate connection name '{conn.name}'")
            seen.add(key)
        return self

    def connection(self, name: str) -> ConnectionCfg:
        wanted = name.casefold()
        for conn in self.connections:
            if conn.name.casefold() == wanted:
                return conn
        known = ", ".join(c.name for c in self.connections)
        raise ConfigError(f"unknown connection '{name}' (configured: {known})")
