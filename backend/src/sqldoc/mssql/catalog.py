"""Catalog extraction: runs the packaged T-SQL against one database at a time."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

from sqldoc.mssql.client import MssqlClient

QUERY_NAMES: tuple[str, ...] = (
    "database_info",
    "objects",
    "table_types",
    "columns",
    "parameters",
    "indexes",
    "index_columns",
    "foreign_keys",
    "foreign_key_columns",
    "check_constraints",
    "extended_properties",
    "modules",
    "triggers",
    "synonyms",
    "dependencies",
    "table_stats",
    "index_usage",
    "proc_stats",
    "missing_indexes",
    "server_info",
    "server_start_time",
    "auth_scheme",
    "permissions",
)

_KIND_BY_TYPE: dict[str, str] = {
    "U": "table",
    "V": "view",
    "P": "procedure",
    "PC": "procedure",
    "FN": "scalar_function",
    "IF": "inline_tvf",
    "TF": "table_function",
    "FS": "clr_function",
    "FT": "clr_function",
    "TR": "trigger",
    "TA": "trigger",
    "SN": "synonym",
    "SO": "sequence",
    "TT": "table_type",
}

_LENGTH_TYPES = {"varchar", "char", "binary", "varbinary"}
_NCHAR_TYPES = {"nvarchar", "nchar"}
_PRECISION_SCALE_TYPES = {"decimal", "numeric"}
_SCALE_TYPES = {"datetime2", "time", "datetimeoffset"}


@cache
def load_sql(name: str) -> str:
    return (resources.files("sqldoc.mssql") / "sql" / f"{name}.sql").read_text(encoding="utf-8")


def object_kind(type_code: str | None) -> str | None:
    if type_code is None:
        return None
    return _KIND_BY_TYPE.get(type_code.strip().upper())


def type_display(
    type_name: str,
    max_length: int | None = None,
    precision: int | None = None,
    scale: int | None = None,
    is_user_defined: bool = False,
    system_type_name: str | None = None,
) -> str:
    """Render a column/parameter type the way SSMS shows it (``nvarchar(50)``)."""
    if is_user_defined:
        return type_name
    t = type_name.lower()
    if t in _NCHAR_TYPES:
        return f"{t}(max)" if max_length == -1 else f"{t}({(max_length or 0) // 2})"
    if t in _LENGTH_TYPES:
        return f"{t}(max)" if max_length == -1 else f"{t}({max_length})"
    if t in _PRECISION_SCALE_TYPES:
        return f"{t}({precision},{scale})"
    if t in _SCALE_TYPES:
        return f"{t}({scale})"
    return t


@dataclass
class RawDatabase:
    """Everything the catalog says about one database (row dicts, unfiltered)."""

    name: str
    info: dict[str, Any]
    objects: list[dict[str, Any]] = field(default_factory=list)
    columns: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(default_factory=list)
    index_columns: list[dict[str, Any]] = field(default_factory=list)
    foreign_keys: list[dict[str, Any]] = field(default_factory=list)
    foreign_key_columns: list[dict[str, Any]] = field(default_factory=list)
    check_constraints: list[dict[str, Any]] = field(default_factory=list)
    extended_properties: list[dict[str, Any]] = field(default_factory=list)
    modules: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[dict[str, Any]] = field(default_factory=list)
    synonyms: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)


class CatalogExtractor:
    """Runs catalog queries against the client's *current* database."""

    def __init__(self, client: MssqlClient) -> None:
        self.client = client

    def run(self, name: str) -> list[dict[str, Any]]:
        return self.client.query(load_sql(name))

    # -- enumeration (cheap, whole database) --------------------------------------
    def database_info(self) -> dict[str, Any]:
        rows = self.run("database_info")
        return rows[0] if rows else {}

    def objects(self) -> list[dict[str, Any]]:
        """User objects plus table types (which sys.objects hides behind TT_* names)."""
        return self.run("objects") + self.run("table_types")

    def triggers(self) -> list[dict[str, Any]]:
        return self.run("triggers")

    def synonyms(self) -> list[dict[str, Any]]:
        return self.run("synonyms")

    def dependencies(self) -> list[dict[str, Any]]:
        return self.run("dependencies")

    def foreign_keys(self) -> list[dict[str, Any]]:
        return self.run("foreign_keys")

    # -- details -------------------------------------------------------------------
    def details(self, raw: RawDatabase) -> RawDatabase:
        raw.columns = self.run("columns")
        raw.parameters = self.run("parameters")
        raw.indexes = self.run("indexes")
        raw.index_columns = self.run("index_columns")
        raw.foreign_key_columns = self.run("foreign_key_columns")
        raw.check_constraints = self.run("check_constraints")
        raw.extended_properties = self.run("extended_properties")
        raw.modules = self.run("modules")
        return raw

    # -- server-level probes --------------------------------------------------------
    def server_info(self) -> dict[str, Any]:
        rows = self.run("server_info")
        return rows[0] if rows else {}

    def server_start_time(self) -> Any:
        return self.client.scalar(load_sql("server_start_time"))

    def auth_scheme(self) -> str | None:
        return self.client.scalar(load_sql("auth_scheme"))

    def permissions(self) -> dict[str, bool]:
        rows = self.run("permissions")
        return {k: bool(v) for k, v in (rows[0] if rows else {}).items()}
