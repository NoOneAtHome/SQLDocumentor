"""Thin DB-API wrapper used by all catalog/stats extraction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqldoc.config.schema import ConnectionCfg
from sqldoc.mssql.driver import Driver, select_driver


def quote_ident(name: str) -> str:
    """Bracket-quote a SQL Server identifier."""
    return "[" + name.replace("]", "]]") + "]"


class MssqlClient:
    """Runs queries written with ``?`` placeholders against any supported driver.

    Note: for ``pyformat`` drivers the ``?`` -> ``%s`` translation is textual, so
    parametrised queries must not contain a literal ``?``.
    """

    def __init__(self, connection: Any, paramstyle: str, driver_name: str = "unknown") -> None:
        self._conn = connection
        self._paramstyle = paramstyle
        self.driver_name = driver_name
        self.current_database: str | None = None

    # -- querying -----------------------------------------------------------------
    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        cur = self._conn.cursor()
        try:
            cur.execute(*self._prepare(sql, params))
            if not cur.description:
                return []
            names = [d[0] for d in cur.description]
            return [dict(zip(names, row, strict=False)) for row in cur.fetchall()]
        finally:
            cur.close()

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        rows = self.query(sql, params)
        if not rows:
            return None
        return next(iter(rows[0].values()))

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        cur = self._conn.cursor()
        try:
            cur.execute(*self._prepare(sql, params))
        finally:
            cur.close()

    def _prepare(self, sql: str, params: Sequence[Any] | None) -> tuple[Any, ...]:
        if params is None:
            return (sql, None)
        if self._paramstyle == "pyformat":
            sql = sql.replace("%", "%%").replace("?", "%s")
        return (sql, tuple(params))

    # -- database context ---------------------------------------------------------
    def use_database(self, name: str) -> None:
        self.execute(f"USE {quote_ident(name)}")
        self.current_database = name

    # -- lifecycle ----------------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> MssqlClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def connect(cfg: ConnectionCfg, database: str, driver: Driver | None = None) -> MssqlClient:
    """Open a client for ``database`` on the configured connection."""
    driver = driver or select_driver(cfg)
    secret = cfg.auth.password.get_secret_value() if cfg.auth.password else None
    raw = driver.connect(cfg, database, secret)
    client = MssqlClient(raw, paramstyle=driver.paramstyle, driver_name=driver.name)
    client.current_database = database
    return client
