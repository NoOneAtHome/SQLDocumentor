"""Lineage scan phase: analyze every object with a definition and persist the results.

Produces ``column_lineage`` edges, ``parsed_*`` object dependencies, pseudo
objects for #temp tables / @table variables, result-set and RETURN_VALUE pseudo
columns, computed-column edges, and ``lineage_issues``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlglot import parse_one
from sqlglot.errors import ErrorLevel

from sqldoc.lineage.engine import (
    ColumnEdge,
    Issue,
    LineageResult,
    ObjectRefEdge,
    QueryAnalyzer,
    analyze_module,
    analyze_view,
)
from sqldoc.lineage.schema_builder import TEMP_SCHEMA, LineageCatalog, TableKey
from sqldoc.mssql.client import quote_ident
from sqldoc.scan.progress import ScanProgress
from sqldoc.store import models as m
from sqldoc.store.writer import SnapshotWriter

MAX_DEFINITION_CHARS = 500_000
RELATION_KINDS = frozenset({"table", "view", "inline_tvf", "table_function", "table_type"})
ANALYZE_ORDER = ("view", "inline_tvf", "table_function", "procedure", "trigger", "scalar_function")
_REF_KIND = {
    "read": "parsed_read",
    "write": "parsed_write",
    "exec": "parsed_exec",
    "function": "parsed_read",
}


@dataclass
class _Index:
    objects: dict[int, m.DbObject]
    by_name: dict[tuple[str, str, str], m.DbObject]
    columns: dict[int, list[m.Column]] = field(default_factory=lambda: defaultdict(list))

    def find(self, key: TableKey) -> m.DbObject | None:
        return self.by_name.get(key.norm)

    def column(self, object_id: int, name: str) -> m.Column | None:
        wanted = name.casefold()
        for c in self.columns.get(object_id, ()):
            if c.name.casefold() == wanted:
                return c
        return None


def run_lineage(
    session: Session,
    writer: SnapshotWriter,
    raws: dict,
    progress: ScanProgress,
) -> None:
    scan_id = writer.scan_id
    index = _load(session, scan_id)
    default_db = next(iter(raws), None) or next(
        (o.database_name for o in index.objects.values() if o.database_name), "master"
    )
    catalog = LineageCatalog(default_db)
    for o in index.objects.values():
        if o.kind in RELATION_KINDS and o.database_name and o.schema_name:
            catalog.add_table(
                o.database_name, o.schema_name, o.name, [c.name for c in index.columns[o.id]]
            )

    targets = sorted(
        (o for o in index.objects.values() if o.kind in ANALYZE_ORDER and o.definition),
        key=lambda o: (ANALYZE_ORDER.index(o.kind), o.schema_name or "", o.name),
    )
    progress.start_phase("lineage", total=len(targets))
    persister = _Persister(session, scan_id, writer.connection_name, index)
    for n, o in enumerate(targets, start=1):
        progress.check_cancelled()
        progress.advance(message=f"{o.schema_name}.{o.name}")
        if len(o.definition or "") > MAX_DEFINITION_CHARS:
            persister.issue(
                o, Issue("skipped", f"definition longer than {MAX_DEFINITION_CHARS} chars")
            )
            o.lineage_status = "skipped"
            continue
        try:
            result = _analyze(o, index, catalog)
        except Exception as exc:  # noqa: BLE001 - one object must never fail the phase
            persister.issue(o, Issue("unsupported", f"{exc.__class__.__name__}: {str(exc)[:400]}"))
            o.lineage_status = "failed"
            continue
        persister.persist(o, result)
        if n % 50 == 0:
            session.commit()
    _computed_columns(index, catalog, persister)
    session.flush()


def _load(session: Session, scan_id: int) -> _Index:
    objects = (
        session.execute(select(m.DbObject).where(m.DbObject.scan_id == scan_id)).scalars().all()
    )
    by_id = {o.id: o for o in objects}
    by_name = {
        (o.database_name.casefold(), o.schema_name.casefold(), o.name.casefold()): o
        for o in objects
        if o.database_name and o.schema_name and o.kind != "external"
    }
    index = _Index(by_id, by_name)
    columns = session.execute(
        select(m.Column)
        .where(m.Column.scan_id == scan_id, m.Column.column_kind == "column")
        .order_by(m.Column.object_id, m.Column.ordinal)
    ).scalars()
    for c in columns:
        index.columns[c.object_id].append(c)
    return index


def _analyze(o: m.DbObject, index: _Index, catalog: LineageCatalog) -> LineageResult:
    names = [c.name for c in index.columns[o.id]]
    database = o.database_name or catalog.default_db
    if o.kind == "view":
        return analyze_view(o.definition, database=database, output_columns=names, catalog=catalog)
    parent_table = None
    output_columns: list[str] | None = None
    if o.kind == "trigger" and o.parent_object_id is not None:
        parent = index.objects.get(o.parent_object_id)
        if parent is not None and parent.schema_name:
            parent_table = TableKey(
                parent.database_name or database, parent.schema_name, parent.name
            )
    if o.kind in ("inline_tvf", "table_function"):
        output_columns = names
    if o.kind == "scalar_function":
        output_columns = ["RETURN_VALUE"]
    return analyze_module(
        o.definition,
        kind=o.kind,
        database=database,
        schema=o.schema_name or "dbo",
        name=o.name,
        catalog=catalog,
        output_columns=output_columns,
        parent_table=parent_table,
    )


def _computed_columns(index: _Index, catalog: LineageCatalog, persister: _Persister) -> None:
    analyzers: dict[str, QueryAnalyzer] = {}
    for o in index.objects.values():
        if o.kind != "table" or not o.schema_name:
            continue
        for c in index.columns[o.id]:
            if not c.computed_definition:
                continue
            db = o.database_name or catalog.default_db
            analyzer = analyzers.setdefault(db, QueryAnalyzer(catalog, db))
            sql = (
                f"SELECT {c.computed_definition} AS {quote_ident(c.name)} "
                f"FROM {quote_ident(o.schema_name)}.{quote_ident(o.name)}"
            )
            try:
                ql = analyzer.analyze(parse_one(sql, read="tsql", error_level=ErrorLevel.RAISE), 0)
            except Exception as exc:  # noqa: BLE001
                persister.issue(
                    o, Issue("parse_error", f"computed column {c.name}: {str(exc)[:300]}")
                )
                continue
            for out in ql.outputs:
                for hit in out.hits:
                    if hit.table is None or hit.column in (None, "*"):
                        continue
                    persister.edge(
                        o,
                        ColumnEdge(
                            target_column=c.name,
                            target_index=None,
                            source_table=hit.table,
                            source_name=None,
                            source_column=hit.column,
                            confidence="inferred",
                            transform="computed",
                            expression_sql=c.computed_definition[:2000],
                            statement_index=None,
                            statement_kind="computed",
                        ),
                    )
            for ref in ql.functions:
                persister.ref(o, ref)


class _Persister:
    def __init__(self, session: Session, scan_id: int, connection: str, index: _Index) -> None:
        self.session = session
        self.scan_id = scan_id
        self.connection = connection
        self.index = index
        self._pseudo: dict[tuple[int, str], m.DbObject] = {}
        self._seen_edges: set[tuple] = set()
        self._seen_refs: set[tuple] = set()

    # -- entry -------------------------------------------------------------------------
    def persist(self, o: m.DbObject, result: LineageResult) -> None:
        for idx, names in enumerate(result.resultsets):
            for ordinal, name in enumerate(names, start=1):
                self._pseudo_column(o, name, "resultset", ordinal, idx)
        for e in result.column_edges:
            self.edge(o, e)
        for r in result.object_refs:
            self.ref(o, r)
        for i in result.issues:
            self.issue(o, i)
        o.has_dynamic_sql = bool(result.has_dynamic_sql)
        o.lineage_status = result.status
        self.session.flush()

    def issue(self, o: m.DbObject, i: Issue) -> None:
        self.session.add(
            m.LineageIssue(
                scan_id=self.scan_id,
                object_id=o.id,
                statement_index=i.statement_index,
                kind=i.kind,
                message=i.message[:2000],
                snippet=i.snippet,
            )
        )

    # -- edges -------------------------------------------------------------------------
    def edge(self, o: m.DbObject, e: ColumnEdge) -> None:
        target = self._target(o, e)
        if target is None:
            return
        target_obj, target_col = target
        source_obj_id, source_col_id, source_name = self._source(o, e)
        key = (
            source_obj_id,
            source_col_id,
            source_name,
            target_col.id,
            e.statement_index,
            e.transform,
        )
        if key in self._seen_edges:
            return
        self._seen_edges.add(key)
        via_object = o.id if e.target_kind in ("table", "temp", "tablevar") else None
        self.session.add(
            m.ColumnLineage(
                scan_id=self.scan_id,
                source_object_id=source_obj_id,
                source_column_id=source_col_id,
                source_column_name=source_name,
                target_object_id=target_obj.id,
                target_column_id=target_col.id,
                via_object_id=via_object,
                confidence=e.confidence,
                transform=e.transform,
                statement_index=e.statement_index,
                statement_kind=e.statement_kind,
                expression_sql=e.expression_sql,
                via=e.via,
            )
        )

    def _target(self, o: m.DbObject, e: ColumnEdge) -> tuple[m.DbObject, m.Column] | None:
        if e.target_kind == "self":
            col = self.index.column(o.id, e.target_column)
            if col is None and o.kind == "scalar_function":
                col = self._pseudo_column(o, e.target_column, "return_value", 1)
            return (o, col) if col else None
        if e.target_kind == "resultset":
            col = self._pseudo_column(o, e.target_column, "resultset", None, e.resultset_index)
            return (o, col)
        if e.target_kind in ("temp", "tablevar"):
            if e.target_table is None:
                return None
            pseudo = self._pseudo_object(o, e.target_kind, e.target_table.name)
            return (pseudo, self._pseudo_column(pseudo, e.target_column, "column", None))
        if e.target_table is None:
            self._unresolved(o, e.target_name, e.statement_index)
            return None
        target = self.index.find(e.target_table)
        if target is None:
            self._unresolved(o, e.target_table.display(), e.statement_index)
            return None
        col = self.index.column(target.id, e.target_column)
        if col is None:
            return None
        return (target, col)

    def _source(self, o: m.DbObject, e: ColumnEdge) -> tuple[int | None, int | None, str | None]:
        if e.source_table is None:
            name = e.source_column
            if e.source_name and name:
                name = f"{e.source_name}.{name}"
            return None, None, name or e.source_name
        if e.source_table.is_pseudo:
            kind = "temp" if e.source_table.schema.casefold() == TEMP_SCHEMA else "tablevar"
            pseudo = self._pseudo_object(o, kind, e.source_table.name)
            if e.source_column in (None, "*"):
                return pseudo.id, None, e.source_column
            col = self._pseudo_column(pseudo, e.source_column, "column", None)
            return pseudo.id, col.id, None
        source = self.index.find(e.source_table)
        if source is None:
            return None, None, f"{e.source_table.display()}.{e.source_column}"
        if e.source_column in (None, "*"):
            return source.id, None, e.source_column
        col = self.index.column(source.id, e.source_column)
        return source.id, (col.id if col else None), (None if col else e.source_column)

    def _unresolved(self, o: m.DbObject, name: str | None, statement_index: int | None) -> None:
        key = ("unresolved", o.id, (name or "").casefold())
        if key in self._seen_refs:
            return
        self._seen_refs.add(key)
        self.issue(
            o,
            Issue("unresolved_ref", f"write target could not be resolved: {name}", statement_index),
        )

    # -- pseudo objects / columns --------------------------------------------------------
    def _pseudo_object(self, owner: m.DbObject, kind: str, name: str) -> m.DbObject:
        display = ("#" if kind == "temp" else "@") + name
        cache_key = (owner.id, display.casefold())
        if cache_key in self._pseudo:
            return self._pseudo[cache_key]
        row = m.DbObject(
            scan_id=self.scan_id,
            database_id=owner.database_id,
            object_key=f"{owner.object_key}|{display}",
            database_name=owner.database_name,
            schema_name=owner.schema_name,
            name=display,
            kind="temp_table",
            scope=owner.scope,
            parent_object_id=owner.id,
            lineage_status="n/a",
        )
        self.session.add(row)
        self.session.flush()
        self._pseudo[cache_key] = row
        self.index.objects[row.id] = row
        return row

    def _pseudo_column(
        self,
        owner: m.DbObject,
        name: str,
        column_kind: str,
        ordinal: int | None,
        resultset_index: int | None = None,
    ) -> m.Column:
        existing = [
            c
            for c in self.index.columns[owner.id]
            if c.name.casefold() == name.casefold()
            and c.column_kind == column_kind
            and c.resultset_index == resultset_index
        ]
        if existing:
            return existing[0]
        suffix = f"#rs{resultset_index}|" if resultset_index is not None else ""
        row = m.Column(
            scan_id=self.scan_id,
            object_id=owner.id,
            column_key=f"{owner.object_key}|{suffix}{name}",
            column_id=None,
            ordinal=ordinal or len(self.index.columns[owner.id]) + 1,
            name=name,
            column_kind=column_kind,
            resultset_index=resultset_index,
        )
        self.session.add(row)
        self.session.flush()
        self.index.columns[owner.id].append(row)
        return row

    # -- object references -------------------------------------------------------------
    def ref(self, o: m.DbObject, r: ObjectRefEdge) -> None:
        edge_kind = _REF_KIND.get(r.kind, "parsed_read")
        target = self.index.find(r.table) if r.table else None
        if target is None and r.kind in ("exec", "function"):
            target = self.index.by_name.get(
                (
                    (r.database or o.database_name or "").casefold(),
                    (r.schema or "dbo").casefold(),
                    r.name.casefold(),
                )
            )
        if target is not None and target.id == o.id:
            return
        key = (o.id, edge_kind, target.id if target else r.display().casefold())
        if key in self._seen_refs:
            return
        self._seen_refs.add(key)
        self.session.add(
            m.ObjectDependency(
                scan_id=self.scan_id,
                source_object_id=o.id,
                target_object_id=target.id if target else None,
                edge_kind=edge_kind,
                resolution="resolved" if target else "unresolved",
                referenced_name=r.display(),
            )
        )
