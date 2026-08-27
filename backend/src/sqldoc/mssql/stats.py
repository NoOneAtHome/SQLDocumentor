"""DMV-based statistics with per-query degradation.

Every family is collected independently; a failure (typically a missing
VIEW SERVER STATE / VIEW DATABASE STATE permission) becomes a warning and the
scan continues. When permissions were probed up front, queries known to need a
missing permission are skipped without being executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqldoc.mssql.catalog import load_sql

# query name -> permission it requires (probe key from permissions.sql)
_REQUIRES: dict[str, str] = {
    "table_stats": "view_database_state",
    "index_usage": "view_database_state",
    "proc_stats": "view_server_state",
    "missing_indexes": "view_server_state",
}


@dataclass(frozen=True)
class StatsWarning:
    code: str  # stats_unavailable | permission_missing
    query: str
    message: str


@dataclass
class RawStats:
    table_stats: list[dict[str, Any]] = field(default_factory=list)
    index_usage: list[dict[str, Any]] = field(default_factory=list)
    proc_stats: list[dict[str, Any]] = field(default_factory=list)
    missing_indexes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[StatsWarning] = field(default_factory=list)


class StatsExtractor:
    def __init__(self, client: Any, permissions: dict[str, bool] | None = None) -> None:
        self.client = client
        self.permissions = permissions or {}

    def collect(self) -> RawStats:
        raw = RawStats()
        for name in ("table_stats", "index_usage", "proc_stats", "missing_indexes"):
            setattr(raw, name, self._run(name, raw.warnings))
        return raw

    def _run(self, name: str, warnings: list[StatsWarning]) -> list[dict[str, Any]]:
        needed = _REQUIRES[name]
        if self.permissions.get(needed) is False:
            warnings.append(
                StatsWarning(
                    "permission_missing",
                    name,
                    f"{name} skipped: login lacks {needed.upper().replace('_', ' ')}",
                )
            )
            return []
        try:
            return self.client.query(load_sql(name))
        except Exception as exc:  # driver errors are not a stable hierarchy across drivers
            warnings.append(
                StatsWarning("stats_unavailable", name, f"{name} failed: {_first_line(exc)}")
            )
            return []


def _first_line(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    return text.splitlines()[0][:500]


def suggested_index_ddl(
    schema: str,
    table: str,
    equality: str | None,
    inequality: str | None,
    included: str | None,
) -> str:
    """Build a CREATE INDEX statement from sys.dm_db_missing_index_details columns."""
    key_parts = [p.strip() for p in f"{equality or ''},{inequality or ''}".split(",") if p.strip()]
    name_parts = [p.strip("[]") for p in key_parts]
    name = "IX_" + "_".join([table, *name_parts])
    ddl = f"CREATE NONCLUSTERED INDEX [{name}] ON [{schema}].[{table}] ({', '.join(key_parts)})"
    if included:
        ddl += f" INCLUDE ({included})"
    return ddl + ";"
