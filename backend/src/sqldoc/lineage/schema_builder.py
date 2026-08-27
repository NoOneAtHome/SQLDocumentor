"""Catalog of known relations (tables, views, TVFs, pseudo tables) for qualification."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sqlglot.schema import MappingSchema

TEMP_SCHEMA = "sqldoc_temp"  # pseudo schema for #temp tables (per analyzed object)
TABLEVAR_SCHEMA = "sqldoc_tablevar"  # pseudo schema for @table variables
PSEUDO_SCHEMAS = frozenset({TEMP_SCHEMA, TABLEVAR_SCHEMA})


@dataclass(frozen=True)
class TableKey:
    db: str
    schema: str
    name: str

    @property
    def norm(self) -> tuple[str, str, str]:
        return (self.db.casefold(), self.schema.casefold(), self.name.casefold())

    @property
    def is_pseudo(self) -> bool:
        return self.schema.casefold() in PSEUDO_SCHEMAS

    def display(self) -> str:
        return f"{self.schema}.{self.name}"


class LineageCatalog:
    """Relations across all configured databases, in original case, keyed case-insensitively."""

    def __init__(self, default_db: str) -> None:
        self.default_db = default_db
        self._tables: dict[tuple[str, str, str], TableKey] = {}
        self._columns: dict[tuple[str, str, str], list[str]] = {}

    def add_table(self, db: str, schema: str, name: str, columns: Iterable[str]) -> TableKey:
        key = TableKey(db, schema, name)
        self._tables[key.norm] = key
        self._columns[key.norm] = list(columns)
        return key

    def remove_table(self, key: TableKey) -> None:
        self._tables.pop(key.norm, None)
        self._columns.pop(key.norm, None)

    def lookup(self, db: str | None, schema: str | None, name: str) -> TableKey | None:
        norm = ((db or self.default_db).casefold(), (schema or "dbo").casefold(), name.casefold())
        return self._tables.get(norm)

    def columns(self, key: TableKey) -> list[str]:
        return list(self._columns.get(key.norm, ()))

    def column_name(self, key: TableKey, column: str) -> str | None:
        """Original-case column name, or None when the column is unknown."""
        wanted = column.casefold()
        for col in self._columns.get(key.norm, ()):
            if col.casefold() == wanted:
                return col
        return None

    def mapping_schema(self) -> MappingSchema:
        nested: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
        for key in self._tables.values():
            cols = self._columns[key.norm]
            nested.setdefault(key.db, {}).setdefault(key.schema, {})[key.name] = {
                c: "unknown" for c in cols
            }
        return MappingSchema(nested, dialect="tsql", normalize=True)

    def tables(self) -> Mapping[tuple[str, str, str], TableKey]:
        return self._tables
