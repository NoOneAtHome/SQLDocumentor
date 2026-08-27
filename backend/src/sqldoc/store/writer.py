"""Persist raw catalog rows and the cascade closure as one immutable snapshot."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from sqldoc.config.schema import DatabaseCfg
from sqldoc.mssql.catalog import RawDatabase, object_kind, type_display
from sqldoc.mssql.identity import column_key, object_key
from sqldoc.mssql.stats import RawStats, suggested_index_ddl
from sqldoc.scope.cascade import Closure, ObjId
from sqldoc.store import models as m

_HAS_DEFINITION = {
    "view",
    "procedure",
    "scalar_function",
    "inline_tvf",
    "table_function",
    "trigger",
}


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


class SnapshotWriter:
    """Writes one scan. Call the ``write_*`` methods in order, per database."""

    def __init__(self, session: Session, scan_id: int, connection_name: str) -> None:
        self.session = session
        self.scan_id = scan_id
        self.connection_name = connection_name
        self._db_rows: dict[str, m.SnapshotDatabase] = {}
        self._obj_ids: dict[ObjId, int] = {}
        self._obj_kinds: dict[ObjId, str] = {}
        self._col_ids: dict[tuple[str, int, int], int] = {}
        self._ext_ids: dict[str, int] = {}
        self._obj_names: dict[ObjId, tuple[str, str]] = {}
        self._index_rows: dict[tuple[str, int, int], m.IndexDef] = {}

    # -- lookups used by later phases -------------------------------------------------
    def object_id(self, db: str, sql_object_id: int) -> int | None:
        return self._obj_ids.get((db, sql_object_id))

    def column_id(self, db: str, sql_object_id: int, column_id: int) -> int | None:
        return self._col_ids.get((db, sql_object_id, column_id))

    def external_id(self, key: str) -> int | None:
        return self._ext_ids.get(key)

    def object_ids(self) -> dict[ObjId, int]:
        return dict(self._obj_ids)

    # -- phases -------------------------------------------------------------------------
    def write_database(
        self,
        raw: RawDatabase,
        db_cfg: DatabaseCfg | None,
        permissions: dict[str, bool] | None = None,
    ) -> m.SnapshotDatabase:
        perms = permissions or {}
        row = m.SnapshotDatabase(
            scan_id=self.scan_id,
            name=raw.name,
            database_id=raw.info.get("database_id"),
            collation=raw.info.get("collation_name"),
            compatibility_level=raw.info.get("compatibility_level"),
            is_configured=db_cfg is not None,
            selected_schemas_json=json.dumps(db_cfg.schemas) if db_cfg else None,
            has_view_definition=perms.get("view_definition"),
            has_view_database_state=perms.get("view_database_state"),
        )
        self.session.add(row)
        self.session.flush()
        self._db_rows[raw.name] = row
        return row

    def write_objects(self, raw: RawDatabase, closure: Closure) -> None:
        db = raw.name
        db_row = self._db_rows[db]
        descriptions = _descriptions(raw.extended_properties, klass=1, minor=0)
        modules = {r["object_id"]: r for r in raw.modules}
        triggers = {r["object_id"]: r for r in raw.triggers}
        pending: list[tuple[m.DbObject, int | None]] = []

        for r in raw.objects:
            oid: ObjId = (db, int(r["object_id"]))
            scope = closure.scope.get(oid)
            if scope is None:
                continue
            kind = object_kind(r["type"])
            if kind is None:
                continue
            module = modules.get(oid[1])
            trigger = triggers.get(oid[1])
            row = m.DbObject(
                scan_id=self.scan_id,
                database_id=db_row.id,
                object_key=object_key(self.connection_name, db, r["schema_name"], r["name"]),
                database_name=db,
                schema_name=r["schema_name"],
                name=r["name"],
                kind=kind,
                sql_object_id=oid[1],
                scope=scope,
                create_date=r.get("create_date"),
                modify_date=r.get("modify_date"),
                description=descriptions.get(oid[1]),
                definition=module.get("definition") if module else None,
                uses_ansi_nulls=_bool(module, "uses_ansi_nulls"),
                uses_quoted_identifier=_bool(module, "uses_quoted_identifier"),
                is_schema_bound=_bool(module, "is_schema_bound"),
                is_instead_of_trigger=_bool(trigger, "is_instead_of_trigger"),
                trigger_events=trigger.get("events") if trigger else None,
                is_disabled=_bool(trigger, "is_disabled"),
                lineage_status="pending" if kind in _HAS_DEFINITION else "n/a",
            )
            self.session.add(row)
            parent = r.get("parent_object_id")
            pending.append((row, int(parent) if parent else None))
            self._obj_kinds[oid] = kind
            self._obj_names[oid] = (r["schema_name"], r["name"])

        self.session.flush()
        for row, _parent in pending:
            self._obj_ids[(db, row.sql_object_id)] = row.id
        for row, parent in pending:
            if parent is not None:
                row.parent_object_id = self._obj_ids.get((db, parent))
        self.session.flush()

    def write_externals(self, closure: Closure) -> None:
        for key, ref in closure.externals.items():
            if key in self._ext_ids:
                continue
            row = m.DbObject(
                scan_id=self.scan_id,
                database_id=None,
                object_key=key,
                database_name=ref.database,
                schema_name=ref.schema,
                name=ref.name,
                kind="external",
                scope="external",
                external_server=ref.server,
                lineage_status="n/a",
            )
            self.session.add(row)
            self.session.flush()
            self._ext_ids[key] = row.id

    def write_details(self, raw: RawDatabase) -> None:
        db = raw.name
        self._write_columns(db, raw)
        self._write_parameters(db, raw)
        self._write_indexes(db, raw)
        self._write_foreign_keys(db, raw)
        self._write_check_constraints(db, raw)
        self.session.flush()

    def write_dependencies(self, closure: Closure) -> None:
        for e in closure.edges:
            source = self._obj_ids.get(e.source)
            if source is None:
                continue
            target = None
            if e.target is not None:
                target = self._obj_ids.get(e.target)
                if target is None:
                    continue
            elif e.external_key is not None:
                target = self._ext_ids.get(e.external_key)
            referencing_column_id = None
            if e.referencing_minor_id:
                referencing_column_id = self._col_ids.get(
                    (e.source[0], e.source[1], e.referencing_minor_id)
                )
            self.session.add(
                m.ObjectDependency(
                    scan_id=self.scan_id,
                    source_object_id=source,
                    target_object_id=target,
                    edge_kind=e.kind,
                    resolution=e.resolution,
                    is_ambiguous=e.is_ambiguous,
                    is_caller_dependent=e.is_caller_dependent,
                    is_schema_bound=e.is_schema_bound,
                    referencing_column_id=referencing_column_id,
                    referenced_name=e.referenced_name,
                )
            )
        self.session.flush()

    def write_stats(self, db: str, stats: RawStats) -> None:
        for r in stats.table_stats:
            obj_id = self._obj_ids.get((db, int(r["object_id"])))
            if obj_id is None:
                continue
            lo, hi = r.get("compression_min"), r.get("compression_max")
            self.session.add(
                m.TableStats(
                    scan_id=self.scan_id,
                    object_id=obj_id,
                    row_count=r.get("row_count"),
                    data_kb=r.get("data_kb"),
                    index_kb=r.get("index_kb"),
                    reserved_kb=r.get("reserved_kb"),
                    partition_count=r.get("partition_count"),
                    is_heap=_b(r.get("is_heap")),
                    compression=lo if lo == hi else "MIXED",
                )
            )

        usage_by_index = {(int(r["object_id"]), int(r["index_id"])): r for r in stats.index_usage}
        for (idb, sql_oid, index_id), idx in self._index_rows.items():
            if idb != db:
                continue
            u = usage_by_index.get((sql_oid, index_id), {})
            seeks, scans, lookups = (
                int(u.get(k) or 0) for k in ("user_seeks", "user_scans", "user_lookups")
            )
            eligible = (
                not idx.is_primary_key
                and not idx.is_unique_constraint
                and (idx.type_code or 0) >= 2
            )
            self.session.add(
                m.IndexUsage(
                    scan_id=self.scan_id,
                    index_id=idx.id,
                    user_seeks=seeks,
                    user_scans=scans,
                    user_lookups=lookups,
                    user_updates=int(u.get("user_updates") or 0),
                    last_user_seek=u.get("last_user_seek"),
                    last_user_scan=u.get("last_user_scan"),
                    last_user_lookup=u.get("last_user_lookup"),
                    last_user_update=u.get("last_user_update"),
                    is_unused=eligible and seeks + scans + lookups == 0,
                )
            )

        for r in stats.proc_stats:
            obj_id = self._obj_ids.get((db, int(r["object_id"])))
            if obj_id is None:
                continue
            count = int(r.get("execution_count") or 0)
            total = int(r.get("total_elapsed_us") or 0)
            self.session.add(
                m.ProcStats(
                    scan_id=self.scan_id,
                    object_id=obj_id,
                    execution_count=count,
                    total_elapsed_us=total,
                    avg_elapsed_us=total // count if count else None,
                    min_elapsed_us=r.get("min_elapsed_us"),
                    max_elapsed_us=r.get("max_elapsed_us"),
                    total_cpu_us=r.get("total_cpu_us"),
                    total_logical_reads=r.get("total_logical_reads"),
                    last_execution_time=r.get("last_execution_time"),
                    cached_time=r.get("cached_time"),
                )
            )

        for r in stats.missing_indexes:
            sql_oid = int(r["object_id"])
            obj_id = self._obj_ids.get((db, sql_oid))
            if obj_id is None:
                continue
            schema, name = self._obj_names[(db, sql_oid)]
            cost = float(r.get("avg_total_user_cost") or 0)
            impact = float(r.get("avg_user_impact") or 0)
            seeks = int(r.get("user_seeks") or 0) + int(r.get("user_scans") or 0)
            self.session.add(
                m.MissingIndex(
                    scan_id=self.scan_id,
                    object_id=obj_id,
                    index_handle=r.get("index_handle"),
                    equality_columns=r.get("equality_columns"),
                    inequality_columns=r.get("inequality_columns"),
                    included_columns=r.get("included_columns"),
                    unique_compiles=r.get("unique_compiles"),
                    user_seeks=r.get("user_seeks"),
                    user_scans=r.get("user_scans"),
                    last_user_seek=r.get("last_user_seek"),
                    avg_total_user_cost=cost,
                    avg_user_impact=impact,
                    improvement_measure=cost * impact * seeks,
                    suggested_ddl=suggested_index_ddl(
                        schema,
                        name,
                        r.get("equality_columns"),
                        r.get("inequality_columns"),
                        r.get("included_columns"),
                    ),
                )
            )
        self.session.flush()

    # -- detail writers -----------------------------------------------------------------
    def _write_columns(self, db: str, raw: RawDatabase) -> None:
        descriptions = _column_descriptions(raw.extended_properties)
        rows: list[tuple[m.Column, int, int]] = []
        for r in raw.columns:
            sql_oid = int(r["object_id"])
            obj_id = self._obj_ids.get((db, sql_oid))
            if obj_id is None:
                continue
            schema, name = self._obj_names[(db, sql_oid)]
            okey = object_key(self.connection_name, db, schema, name)
            row = m.Column(
                scan_id=self.scan_id,
                object_id=obj_id,
                column_key=column_key(okey, r["name"]),
                column_id=int(r["column_id"]),
                ordinal=int(r["column_id"]),
                name=r["name"],
                column_kind="column",
                type_name=r.get("type_name"),
                type_display=type_display(
                    r.get("type_name") or "",
                    r.get("max_length"),
                    r.get("precision"),
                    r.get("scale"),
                    bool(r.get("is_user_defined")),
                    r.get("system_type_name"),
                ),
                system_type_name=r.get("system_type_name"),
                type_schema=r.get("type_schema"),
                is_user_defined_type=bool(r.get("is_user_defined")),
                max_length=r.get("max_length"),
                precision=r.get("precision"),
                scale=r.get("scale"),
                is_nullable=_b(r.get("is_nullable")),
                is_identity=_b(r.get("is_identity")),
                identity_seed=_str_or_none(r.get("seed_value")),
                identity_increment=_str_or_none(r.get("increment_value")),
                is_computed=_b(r.get("is_computed")),
                computed_definition=r.get("computed_definition"),
                is_persisted=_b(r.get("is_persisted")),
                default_name=r.get("default_name"),
                default_definition=r.get("default_definition"),
                collation_name=r.get("collation_name"),
                is_rowguidcol=_b(r.get("is_rowguidcol")),
                generated_always_type=r.get("generated_always_type"),
                description=descriptions.get((sql_oid, int(r["column_id"]))),
            )
            self.session.add(row)
            rows.append((row, sql_oid, int(r["column_id"])))
        self.session.flush()
        for row, sql_oid, col_id in rows:
            self._col_ids[(db, sql_oid, col_id)] = row.id

    def _write_parameters(self, db: str, raw: RawDatabase) -> None:
        descriptions = _descriptions_by_minor(raw.extended_properties, klass=2)
        for r in raw.parameters:
            obj_id = self._obj_ids.get((db, int(r["object_id"])))
            if obj_id is None:
                continue
            pid = int(r["parameter_id"])
            self.session.add(
                m.Parameter(
                    scan_id=self.scan_id,
                    object_id=obj_id,
                    parameter_id=pid,
                    name=r.get("name") or "",
                    type_name=r.get("type_name"),
                    type_display=type_display(
                        r.get("type_name") or "",
                        r.get("max_length"),
                        r.get("precision"),
                        r.get("scale"),
                        bool(r.get("is_user_defined")),
                        r.get("system_type_name"),
                    ),
                    max_length=r.get("max_length"),
                    precision=r.get("precision"),
                    scale=r.get("scale"),
                    is_output=_b(r.get("is_output")),
                    has_default_value=_b(r.get("has_default_value")),
                    default_value=_str_or_none(r.get("default_value")),
                    is_readonly=_b(r.get("is_readonly")),
                    is_table_type=_b(r.get("is_table_type")),
                    is_return_value=pid == 0,
                    description=descriptions.get((int(r["object_id"]), pid)),
                )
            )

    def _write_indexes(self, db: str, raw: RawDatabase) -> None:
        descriptions = _descriptions_by_minor(raw.extended_properties, klass=7)
        index_rows: dict[tuple[int, int], m.IndexDef] = {}
        for r in raw.indexes:
            sql_oid = int(r["object_id"])
            obj_id = self._obj_ids.get((db, sql_oid))
            if obj_id is None:
                continue
            row = m.IndexDef(
                scan_id=self.scan_id,
                object_id=obj_id,
                index_id=int(r["index_id"]),
                name=r.get("name"),
                type_code=r.get("type"),
                type_desc=r.get("type_desc"),
                is_unique=_b(r.get("is_unique")),
                is_primary_key=_b(r.get("is_primary_key")),
                is_unique_constraint=_b(r.get("is_unique_constraint")),
                has_filter=_b(r.get("has_filter")),
                filter_definition=r.get("filter_definition"),
                fill_factor=r.get("fill_factor"),
                is_disabled=_b(r.get("is_disabled")),
                is_padded=_b(r.get("is_padded")),
                data_space_name=r.get("data_space_name"),
                data_space_type=r.get("data_space_type"),
                description=descriptions.get((sql_oid, int(r["index_id"]))),
            )
            self.session.add(row)
            index_rows[(sql_oid, int(r["index_id"]))] = row
            self._index_rows[(db, sql_oid, int(r["index_id"]))] = row
        self.session.flush()
        for r in raw.index_columns:
            idx = index_rows.get((int(r["object_id"]), int(r["index_id"])))
            if idx is None:
                continue
            self.session.add(
                m.IndexColumn(
                    scan_id=self.scan_id,
                    index_id=idx.id,
                    column_id=self._col_ids.get((db, int(r["object_id"]), int(r["column_id"]))),
                    column_name=r["column_name"],
                    key_ordinal=r.get("key_ordinal"),
                    is_descending=_b(r.get("is_descending_key")),
                    is_included=_b(r.get("is_included_column")),
                    partition_ordinal=r.get("partition_ordinal"),
                )
            )

    def _write_foreign_keys(self, db: str, raw: RawDatabase) -> None:
        fk_rows: dict[int, m.ForeignKeyDef] = {}
        for r in raw.foreign_keys:
            parent = self._obj_ids.get((db, int(r["parent_object_id"])))
            referenced = self._obj_ids.get((db, int(r["referenced_object_id"])))
            if parent is None or referenced is None:
                continue
            row = m.ForeignKeyDef(
                scan_id=self.scan_id,
                name=r["name"],
                parent_object_id=parent,
                referenced_object_id=referenced,
                delete_action=r.get("delete_referential_action_desc"),
                update_action=r.get("update_referential_action_desc"),
                is_disabled=_b(r.get("is_disabled")),
                is_not_trusted=_b(r.get("is_not_trusted")),
            )
            self.session.add(row)
            fk_rows[int(r["object_id"])] = row
        self.session.flush()
        for r in raw.foreign_key_columns:
            fk = fk_rows.get(int(r["constraint_object_id"]))
            if fk is None:
                continue
            self.session.add(
                m.ForeignKeyColumn(
                    scan_id=self.scan_id,
                    foreign_key_id=fk.id,
                    ordinal=int(r["constraint_column_id"]),
                    parent_column_id=self._col_ids.get(
                        (db, int(r["parent_object_id"]), int(r["parent_column_id"]))
                    ),
                    parent_column_name=r["parent_column"],
                    referenced_column_id=self._col_ids.get(
                        (db, int(r["referenced_object_id"]), int(r["referenced_column_id"]))
                    ),
                    referenced_column_name=r["referenced_column"],
                )
            )

    def _write_check_constraints(self, db: str, raw: RawDatabase) -> None:
        for r in raw.check_constraints:
            parent_oid = int(r["parent_object_id"])
            obj_id = self._obj_ids.get((db, parent_oid))
            if obj_id is None:
                continue
            col = r.get("parent_column_id") or 0
            self.session.add(
                m.CheckConstraintDef(
                    scan_id=self.scan_id,
                    object_id=obj_id,
                    column_id=self._col_ids.get((db, parent_oid, int(col))) if col else None,
                    name=r["name"],
                    definition=r.get("definition"),
                    is_disabled=_b(r.get("is_disabled")),
                    is_not_trusted=_b(r.get("is_not_trusted")),
                )
            )


def _b(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _bool(row: dict[str, Any] | None, key: str) -> bool | None:
    return _b(row.get(key)) if row else None


def _descriptions(rows: Iterable[dict[str, Any]], klass: int, minor: int) -> dict[int, str]:
    return {
        int(r["major_id"]): r["value"]
        for r in rows
        if int(r["class"]) == klass and int(r["minor_id"]) == minor
    }


def _column_descriptions(rows: Iterable[dict[str, Any]]) -> dict[tuple[int, int], str]:
    return {
        (int(r["major_id"]), int(r["minor_id"])): r["value"]
        for r in rows
        if int(r["class"]) == 1 and int(r["minor_id"]) > 0
    }


def _descriptions_by_minor(
    rows: Iterable[dict[str, Any]], klass: int
) -> dict[tuple[int, int], str]:
    return {
        (int(r["major_id"]), int(r["minor_id"])): r["value"]
        for r in rows
        if int(r["class"]) == klass
    }
