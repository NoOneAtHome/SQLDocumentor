"""Per-object symbol table for #temp tables and @table variables.

Pseudo relations are registered in the shared LineageCatalog under the
``sqldoc_temp`` / ``sqldoc_tablevar`` pseudo schemas for the duration of one
object's analysis and removed afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqldoc.lineage.schema_builder import TABLEVAR_SCHEMA, TEMP_SCHEMA, LineageCatalog, TableKey


class SymbolTable:
    def __init__(self, catalog: LineageCatalog, database: str) -> None:
        self.catalog = catalog
        self.database = database
        self._registered: list[TableKey] = []
        self._replaced: list[tuple[TableKey, list[str]]] = []

    def _schema_for(self, kind: str) -> str:
        return TEMP_SCHEMA if kind == "temp" else TABLEVAR_SCHEMA

    def key(self, kind: str, name: str) -> TableKey:
        return TableKey(self.database, self._schema_for(kind), name.lstrip("#@"))

    def known(self, kind: str, name: str) -> TableKey | None:
        return self.catalog.lookup(self.database, self._schema_for(kind), name.lstrip("#@"))

    def define(self, kind: str, name: str, columns: Sequence[str]) -> TableKey:
        """Register (or redefine) a pseudo relation with the given columns."""
        existing = self.known(kind, name)
        if existing is not None:
            self._replaced.append((existing, self.catalog.columns(existing)))
            self.catalog.remove_table(existing)
        key = self.catalog.add_table(
            self.database, self._schema_for(kind), name.lstrip("#@"), columns
        )
        self._registered.append(key)
        return key

    def ensure(self, kind: str, name: str, columns: Sequence[str]) -> TableKey:
        return self.known(kind, name) or self.define(kind, name, columns)

    def cleanup(self) -> None:
        for key in self._registered:
            self.catalog.remove_table(key)
        for key, cols in self._replaced:
            self.catalog.add_table(key.db, key.schema, key.name, cols)
        self._registered.clear()
        self._replaced.clear()
