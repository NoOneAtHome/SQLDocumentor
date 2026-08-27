"""Read (and annotation write) queries behind the HTTP API.

All SQL for the API lives here so routers stay thin. Every function takes a
SQLAlchemy ``Session`` first; results are ORM rows, tuples or small dataclasses -
JSON shaping happens in ``sqldoc.api.build``. Name comparisons are
case-insensitive to match SQL Server's default collation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Select, delete, exists, func, select
from sqlalchemy.orm import Session

from sqldoc.store import models as m

UNSET: Any = object()
LINEAGE_KINDS = ("view", "procedure", "scalar_function", "inline_tvf", "table_function", "trigger")
EXEC_KINDS = (
    "procedure",
    "scalar_function",
    "inline_tvf",
    "table_function",
    "clr_function",
    "trigger",
)
TABLE_KINDS = ("table", "view", "table_type", "temp_table")


def _contains(column, needle: str):
    pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return func.lower(column).like(pattern.lower(), escape="\\")


def _ieq(column, value: str):
    return func.lower(column) == value.lower()


def _count(s: Session, stmt: Select) -> int:
    return int(s.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0)


def _ordered(stmt: Select, column, order: str):
    clause = column.desc() if order == "desc" else column.asc()
    return stmt.order_by(clause.nulls_last())


# -- scans ---------------------------------------------------------------------------------


def get_scan(s: Session, scan_id: int) -> m.Scan | None:
    return s.get(m.Scan, scan_id)


def list_scans(s: Session, connection: str, limit: int, offset: int) -> tuple[list[m.Scan], int]:
    base = select(m.Scan).where(_ieq(m.Scan.connection_name, connection))
    total = _count(s, base)
    rows = (
        s.execute(
            base.order_by(m.Scan.started_at.desc(), m.Scan.id.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def latest_scan(s: Session, connection: str) -> m.Scan | None:
    stmt = (
        select(m.Scan)
        .where(_ieq(m.Scan.connection_name, connection), m.Scan.status == "succeeded")
        .order_by(m.Scan.finished_at.desc(), m.Scan.id.desc())
        .limit(1)
    )
    return s.execute(stmt).scalar_one_or_none()


def delete_scan(s: Session, scan_id: int) -> bool:
    result = s.execute(delete(m.Scan).where(m.Scan.id == scan_id))
    return (result.rowcount or 0) > 0


def scan_warnings(s: Session, scan_id: int) -> list[m.ScanWarning]:
    stmt = select(m.ScanWarning).where(m.ScanWarning.scan_id == scan_id).order_by(m.ScanWarning.id)
    return list(s.execute(stmt).scalars().all())


def scan_counts(s: Session, scan_id: int) -> dict[str, int]:
    def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model).where(model.scan_id == scan_id, *where)
        return int(s.execute(stmt).scalar() or 0)

    kinds = dict(
        s.execute(
            select(m.DbObject.kind, func.count())
            .where(m.DbObject.scan_id == scan_id)
            .group_by(m.DbObject.kind)
        ).all()
    )
    schemas = s.execute(
        select(
            func.count(func.distinct(m.DbObject.database_name + "." + m.DbObject.schema_name))
        ).where(m.DbObject.scan_id == scan_id, m.DbObject.scope != "external")
    ).scalar()
    return {
        "databases": count(m.SnapshotDatabase),
        "schemas": int(schemas or 0),
        "tables": kinds.get("table", 0),
        "views": kinds.get("view", 0),
        "procedures": kinds.get("procedure", 0),
        "functions": sum(
            kinds.get(k, 0)
            for k in ("scalar_function", "inline_tvf", "table_function", "clr_function")
        ),
        "triggers": kinds.get("trigger", 0),
        "synonyms": kinds.get("synonym", 0),
        "externals": kinds.get("external", 0),
        "cascaded": count(m.DbObject, m.DbObject.scope == "cascaded"),
        "columns": count(m.Column),
        "edges_object": count(m.ObjectDependency),
        "edges_column": count(m.ColumnLineage),
        "lineage_issues": count(m.LineageIssue),
        "warnings": count(m.ScanWarning),
    }


def lineage_coverage(s: Session, scan_id: int) -> float | None:
    rows = dict(
        s.execute(
            select(m.DbObject.lineage_status, func.count())
            .where(m.DbObject.scan_id == scan_id, m.DbObject.lineage_status != "n/a")
            .group_by(m.DbObject.lineage_status)
        ).all()
    )
    total = sum(rows.values())
    if not total:
        return None
    return (rows.get("ok", 0) + rows.get("partial", 0)) / total


def warnings_summary(s: Session, scan_id: int) -> dict[str, int]:
    def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model).where(model.scan_id == scan_id, *where)
        return int(s.execute(stmt).scalar() or 0)

    return {
        "lineage_issues": count(m.LineageIssue),
        "unused_indexes": count(m.IndexUsage, m.IndexUsage.is_unused.is_(True)),
        "missing_index_suggestions": count(m.MissingIndex),
        "external_refs": count(m.DbObject, m.DbObject.scope == "external"),
    }


def scan_overview(s: Session, scan_id: int) -> dict[str, Any]:
    dbs = (
        s.execute(
            select(m.SnapshotDatabase)
            .where(m.SnapshotDatabase.scan_id == scan_id)
            .order_by(m.SnapshotDatabase.name)
        )
        .scalars()
        .all()
    )
    rows = s.execute(
        select(m.DbObject.database_name, m.DbObject.schema_name, m.DbObject.kind, func.count())
        .where(m.DbObject.scan_id == scan_id, m.DbObject.scope != "external")
        .group_by(m.DbObject.database_name, m.DbObject.schema_name, m.DbObject.kind)
    ).all()
    per_db: dict[str, dict[str, dict[str, int]]] = {}
    for db_name, schema, kind, n in rows:
        per_db.setdefault((db_name or "").casefold(), {}).setdefault(schema or "", {})[kind] = n
    databases = []
    for db in dbs:
        selected = {x.casefold() for x in json.loads(db.selected_schemas_json or "[]")}
        schemas = per_db.get(db.name.casefold(), {})
        databases.append(
            {
                "name": db.name,
                "is_configured": bool(db.is_configured),
                "schemas": [
                    {
                        "name": name,
                        "is_selected": name.casefold() in selected,
                        "counts_by_kind": dict(sorted(counts.items())),
                    }
                    for name, counts in sorted(schemas.items(), key=lambda kv: kv[0].casefold())
                ],
            }
        )
    return {
        "databases": databases,
        "counts": scan_counts(s, scan_id),
        "lineage_coverage": lineage_coverage(s, scan_id),
        "warnings_summary": warnings_summary(s, scan_id),
        "warnings": scan_warnings(s, scan_id),
    }


# -- objects -------------------------------------------------------------------------------


@dataclass
class ObjectFilter:
    db: str | None = None
    schema: str | None = None
    kind: str | None = None  # comma separated
    scope: str | None = None  # comma separated
    q: str | None = None
    tag: str | None = None
    has_issues: bool | None = None
    sort: str = "name"
    order: str = "asc"
    limit: int = 50
    offset: int = 0


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _scope_filters(stmt: Select, scan_id: int, db: str | None, schema: str | None) -> Select:
    stmt = stmt.where(m.DbObject.scan_id == scan_id)
    if db:
        stmt = stmt.where(_ieq(m.DbObject.database_name, db))
    if schema:
        stmt = stmt.where(_ieq(m.DbObject.schema_name, schema))
    return stmt


def _issues_exist():
    return exists(
        select(m.LineageIssue.id).where(
            m.LineageIssue.scan_id == m.DbObject.scan_id,
            m.LineageIssue.object_id == m.DbObject.id,
        )
    )


def list_objects(s: Session, scan_id: int, f: ObjectFilter) -> tuple[list[m.DbObject], int]:
    o = m.DbObject
    stmt = _scope_filters(select(o), scan_id, f.db, f.schema)
    if kinds := _csv(f.kind):
        stmt = stmt.where(o.kind.in_(kinds))
    if scopes := _csv(f.scope):
        stmt = stmt.where(o.scope.in_(scopes))
    if f.q:
        stmt = stmt.where(_contains(o.name, f.q))
    if f.tag:
        stmt = stmt.where(
            exists(
                select(m.TagAssignment.id)
                .join(m.Tag, m.Tag.id == m.TagAssignment.tag_id)
                .where(
                    m.TagAssignment.target_kind == "object",
                    m.TagAssignment.target_key == o.object_key,
                    _ieq(m.Tag.name, f.tag),
                )
            )
        )
    if f.has_issues is not None:
        stmt = stmt.where(_issues_exist() if f.has_issues else ~_issues_exist())
    total = _count(s, stmt)

    if f.sort in ("rows", "size"):
        stmt = stmt.outerjoin(
            m.TableStats, (m.TableStats.object_id == o.id) & (m.TableStats.scan_id == scan_id)
        )
        column = m.TableStats.row_count if f.sort == "rows" else m.TableStats.reserved_kb
    elif f.sort == "execs":
        stmt = stmt.outerjoin(
            m.ProcStats, (m.ProcStats.object_id == o.id) & (m.ProcStats.scan_id == scan_id)
        )
        column = m.ProcStats.execution_count
    elif f.sort == "modified":
        column = o.modify_date
    elif f.sort == "kind":
        column = o.kind
    elif f.sort == "schema":
        column = func.lower(o.schema_name)
    else:
        column = func.lower(o.name)
    stmt = _ordered(stmt, column, f.order).order_by(
        func.lower(o.schema_name), func.lower(o.name), o.id
    )
    rows = s.execute(stmt.limit(f.limit).offset(f.offset)).scalars().all()
    return list(rows), total


def get_object(s: Session, scan_id: int, object_id: int) -> m.DbObject | None:
    obj = s.get(m.DbObject, object_id)
    return obj if obj is not None and obj.scan_id == scan_id else None


def lookup_object(s: Session, scan_id: int, db: str, schema: str, name: str) -> m.DbObject | None:
    stmt = (
        select(m.DbObject)
        .where(
            m.DbObject.scan_id == scan_id,
            _ieq(m.DbObject.database_name, db),
            _ieq(m.DbObject.schema_name, schema),
            _ieq(m.DbObject.name, name),
        )
        .order_by(m.DbObject.id)
        .limit(1)
    )
    return s.execute(stmt).scalar_one_or_none()


def objects_by_ids(s: Session, scan_id: int, ids: list[int]) -> dict[int, m.DbObject]:
    if not ids:
        return {}
    rows = s.execute(
        select(m.DbObject).where(m.DbObject.scan_id == scan_id, m.DbObject.id.in_(ids))
    ).scalars()
    return {o.id: o for o in rows}


def summary_extras(s: Session, scan_id: int, object_ids: list[int]) -> dict[int, dict[str, Any]]:
    out = {
        oid: {
            "row_count": None,
            "total_size_kb": None,
            "exec_count": None,
            "has_lineage_issues": False,
        }
        for oid in object_ids
    }
    if not object_ids:
        return out
    ts = m.TableStats
    for oid, rows, data, index, reserved in s.execute(
        select(ts.object_id, ts.row_count, ts.data_kb, ts.index_kb, ts.reserved_kb).where(
            ts.scan_id == scan_id, ts.object_id.in_(object_ids)
        )
    ):
        out[oid]["row_count"] = rows
        if reserved is not None:
            out[oid]["total_size_kb"] = reserved
        elif data is not None or index is not None:
            out[oid]["total_size_kb"] = (data or 0) + (index or 0)
    ps = m.ProcStats
    for oid, execs in s.execute(
        select(ps.object_id, ps.execution_count).where(
            ps.scan_id == scan_id, ps.object_id.in_(object_ids)
        )
    ):
        out[oid]["exec_count"] = execs
    for (oid,) in s.execute(
        select(m.LineageIssue.object_id)
        .where(m.LineageIssue.scan_id == scan_id, m.LineageIssue.object_id.in_(object_ids))
        .distinct()
    ):
        out[oid]["has_lineage_issues"] = True
    return out


# -- object detail parts -------------------------------------------------------------------


def columns_for(s: Session, scan_id: int, object_id: int) -> list[m.Column]:
    stmt = (
        select(m.Column)
        .where(m.Column.scan_id == scan_id, m.Column.object_id == object_id)
        .order_by(m.Column.column_kind, m.Column.resultset_index, m.Column.ordinal, m.Column.id)
    )
    return list(s.execute(stmt).scalars().all())


def column_by_name(s: Session, scan_id: int, object_id: int, name: str) -> m.Column | None:
    stmt = (
        select(m.Column)
        .where(
            m.Column.scan_id == scan_id,
            m.Column.object_id == object_id,
            _ieq(m.Column.name, name),
        )
        .order_by(m.Column.id)
        .limit(1)
    )
    return s.execute(stmt).scalar_one_or_none()


def parameters_for(s: Session, scan_id: int, object_id: int) -> list[m.Parameter]:
    stmt = (
        select(m.Parameter)
        .where(m.Parameter.scan_id == scan_id, m.Parameter.object_id == object_id)
        .order_by(m.Parameter.parameter_id, m.Parameter.id)
    )
    return list(s.execute(stmt).scalars().all())


@dataclass
class IndexInfo:
    index: m.IndexDef
    columns: list[m.IndexColumn] = field(default_factory=list)
    usage: m.IndexUsage | None = None


def index_columns_for(
    s: Session, scan_id: int, index_ids: list[int]
) -> dict[int, list[m.IndexColumn]]:
    out: dict[int, list[m.IndexColumn]] = {i: [] for i in index_ids}
    if not index_ids:
        return out
    stmt = (
        select(m.IndexColumn)
        .where(m.IndexColumn.scan_id == scan_id, m.IndexColumn.index_id.in_(index_ids))
        .order_by(
            m.IndexColumn.index_id,
            m.IndexColumn.is_included,
            m.IndexColumn.key_ordinal,
            m.IndexColumn.id,
        )
    )
    for ic in s.execute(stmt).scalars():
        out[ic.index_id].append(ic)
    return out


def indexes_for(s: Session, scan_id: int, object_id: int) -> list[IndexInfo]:
    stmt = (
        select(m.IndexDef, m.IndexUsage)
        .outerjoin(m.IndexUsage, m.IndexUsage.index_id == m.IndexDef.id)
        .where(m.IndexDef.scan_id == scan_id, m.IndexDef.object_id == object_id)
        .order_by(m.IndexDef.index_id, m.IndexDef.id)
    )
    infos = [IndexInfo(index=idx, usage=usage) for idx, usage in s.execute(stmt).all()]
    cols = index_columns_for(s, scan_id, [i.index.id for i in infos])
    for info in infos:
        info.columns = cols.get(info.index.id, [])
    return infos


@dataclass
class ForeignKeyInfo:
    fk: m.ForeignKeyDef
    parent: m.DbObject
    referenced: m.DbObject
    columns: list[m.ForeignKeyColumn] = field(default_factory=list)


def foreign_keys_for(
    s: Session, scan_id: int, object_id: int, direction: Literal["out", "in"] = "out"
) -> list[ForeignKeyInfo]:
    fk = m.ForeignKeyDef
    side = fk.parent_object_id if direction == "out" else fk.referenced_object_id
    fks = list(
        s.execute(
            select(fk).where(fk.scan_id == scan_id, side == object_id).order_by(fk.name, fk.id)
        )
        .scalars()
        .all()
    )
    if not fks:
        return []
    obj_ids = {f.parent_object_id for f in fks} | {f.referenced_object_id for f in fks}
    objs = objects_by_ids(s, scan_id, list(obj_ids))
    cols: dict[int, list[m.ForeignKeyColumn]] = {f.id: [] for f in fks}
    stmt = (
        select(m.ForeignKeyColumn)
        .where(
            m.ForeignKeyColumn.scan_id == scan_id,
            m.ForeignKeyColumn.foreign_key_id.in_(list(cols)),
        )
        .order_by(m.ForeignKeyColumn.foreign_key_id, m.ForeignKeyColumn.ordinal)
    )
    for fkc in s.execute(stmt).scalars():
        cols[fkc.foreign_key_id].append(fkc)
    return [
        ForeignKeyInfo(
            fk=f,
            parent=objs[f.parent_object_id],
            referenced=objs[f.referenced_object_id],
            columns=cols[f.id],
        )
        for f in fks
        if f.parent_object_id in objs and f.referenced_object_id in objs
    ]


def check_constraints_for(s: Session, scan_id: int, object_id: int) -> list[m.CheckConstraintDef]:
    ck = m.CheckConstraintDef
    stmt = select(ck).where(ck.scan_id == scan_id, ck.object_id == object_id).order_by(ck.name)
    return list(s.execute(stmt).scalars().all())


def triggers_for(s: Session, scan_id: int, object_id: int) -> list[m.DbObject]:
    o = m.DbObject
    stmt = (
        select(o)
        .where(o.scan_id == scan_id, o.parent_object_id == object_id, o.kind == "trigger")
        .order_by(func.lower(o.name))
    )
    return list(s.execute(stmt).scalars().all())


def table_stats_for(s: Session, scan_id: int, object_id: int) -> m.TableStats | None:
    stmt = select(m.TableStats).where(
        m.TableStats.scan_id == scan_id, m.TableStats.object_id == object_id
    )
    return s.execute(stmt).scalar_one_or_none()


def proc_stats_for(s: Session, scan_id: int, object_id: int) -> m.ProcStats | None:
    stmt = select(m.ProcStats).where(
        m.ProcStats.scan_id == scan_id, m.ProcStats.object_id == object_id
    )
    return s.execute(stmt).scalar_one_or_none()


def missing_indexes_for(s: Session, scan_id: int, object_id: int) -> list[m.MissingIndex]:
    mi = m.MissingIndex
    stmt = (
        select(mi)
        .where(mi.scan_id == scan_id, mi.object_id == object_id)
        .order_by(mi.improvement_measure.desc().nulls_last(), mi.id)
    )
    return list(s.execute(stmt).scalars().all())


@dataclass
class DependencyInfo:
    dep: m.ObjectDependency
    source: m.DbObject
    target: m.DbObject | None


def dependencies_for(
    s: Session, scan_id: int, object_id: int
) -> tuple[list[DependencyInfo], list[DependencyInfo]]:
    """One-hop catalog view: (what this object uses, what uses this object)."""
    d = m.ObjectDependency
    deps = list(
        s.execute(
            select(d)
            .where(
                d.scan_id == scan_id,
                (d.source_object_id == object_id) | (d.target_object_id == object_id),
            )
            .order_by(d.id)
        )
        .scalars()
        .all()
    )
    ids = {x.source_object_id for x in deps} | {
        x.target_object_id for x in deps if x.target_object_id is not None
    }
    objs = objects_by_ids(s, scan_id, list(ids))
    uses: list[DependencyInfo] = []
    used_by: list[DependencyInfo] = []
    seen: set[tuple] = set()
    for dep in deps:
        target = objs.get(dep.target_object_id) if dep.target_object_id is not None else None
        source = objs.get(dep.source_object_id)
        if source is None:
            continue
        key = (
            dep.source_object_id,
            dep.target_object_id,
            dep.edge_kind,
            dep.resolution,
            dep.referenced_name,
        )
        if key in seen:
            continue
        seen.add(key)
        info = DependencyInfo(dep=dep, source=source, target=target)
        if dep.source_object_id == object_id:
            uses.append(info)
        if dep.target_object_id == object_id and dep.source_object_id != object_id:
            used_by.append(info)
    return uses, used_by


def column_lineage_counts(s: Session, scan_id: int, object_id: int) -> dict[int, tuple[int, int]]:
    """column id -> (upstream edge count, downstream edge count)."""
    cl = m.ColumnLineage
    out: dict[int, tuple[int, int]] = {}
    for cid, n in s.execute(
        select(cl.target_column_id, func.count())
        .where(cl.scan_id == scan_id, cl.target_object_id == object_id)
        .group_by(cl.target_column_id)
    ):
        out[cid] = (n, out.get(cid, (0, 0))[1])
    for cid, n in s.execute(
        select(cl.source_column_id, func.count())
        .where(cl.scan_id == scan_id, cl.source_object_id == object_id)
        .group_by(cl.source_column_id)
    ):
        if cid is not None:
            out[cid] = (out.get(cid, (0, 0))[0], n)
    return out


def column_lineage_confidences(
    s: Session, scan_id: int, object_id: int
) -> dict[int, dict[str, int]]:
    cl = m.ColumnLineage
    out: dict[int, dict[str, int]] = {}
    for col, conf, n in s.execute(
        select(cl.target_column_id, cl.confidence, func.count())
        .where(cl.scan_id == scan_id, cl.target_object_id == object_id)
        .group_by(cl.target_column_id, cl.confidence)
    ):
        out.setdefault(col, {})[conf] = out.get(col, {}).get(conf, 0) + n
    for col, conf, n in s.execute(
        select(cl.source_column_id, cl.confidence, func.count())
        .where(cl.scan_id == scan_id, cl.source_object_id == object_id)
        .group_by(cl.source_column_id, cl.confidence)
    ):
        if col is not None:
            out.setdefault(col, {})[conf] = out.get(col, {}).get(conf, 0) + n
    return out


def lineage_issues_for(s: Session, scan_id: int, object_id: int) -> list[m.LineageIssue]:
    li = m.LineageIssue
    stmt = (
        select(li)
        .where(li.scan_id == scan_id, li.object_id == object_id)
        .order_by(li.statement_index.nulls_first(), li.id)
    )
    return list(s.execute(stmt).scalars().all())


def lineage_issues(
    s: Session, scan_id: int, limit: int, offset: int
) -> tuple[list[tuple[m.LineageIssue, m.DbObject]], int]:
    li, o = m.LineageIssue, m.DbObject
    stmt = select(li, o).join(o, o.id == li.object_id).where(li.scan_id == scan_id)
    total = _count(s, stmt)
    rows = s.execute(
        stmt.order_by(func.lower(o.schema_name), func.lower(o.name), li.statement_index, li.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [(issue, obj) for issue, obj in rows], total


def lineage_summary(s: Session, scan_id: int) -> dict[str, Any]:
    d, cl = m.ObjectDependency, m.ColumnLineage
    objects = int(
        s.execute(
            select(func.count()).select_from(m.DbObject).where(m.DbObject.scan_id == scan_id)
        ).scalar()
        or 0
    )
    edges_by_kind = dict(
        s.execute(
            select(d.edge_kind, func.count()).where(d.scan_id == scan_id).group_by(d.edge_kind)
        ).all()
    )
    by_conf = dict(
        s.execute(
            select(cl.confidence, func.count()).where(cl.scan_id == scan_id).group_by(cl.confidence)
        ).all()
    )
    with_issues = int(
        s.execute(
            select(func.count(func.distinct(m.LineageIssue.object_id))).where(
                m.LineageIssue.scan_id == scan_id
            )
        ).scalar()
        or 0
    )
    return {
        "objects": objects,
        "edges_by_kind": {
            k: edges_by_kind.get(k, 0)
            for k in (
                "catalog",
                "fk",
                "trigger",
                "synonym",
                "parsed_read",
                "parsed_write",
                "parsed_exec",
            )
        },
        "column_edges_by_confidence": {
            k: by_conf.get(k, 0) for k in ("exact", "inferred", "unresolved")
        },
        "lineage_coverage": lineage_coverage(s, scan_id),
        "objects_with_issues": with_issues,
    }


# -- search --------------------------------------------------------------------------------


def search_objects(s: Session, scan_id: int, q: str, limit: int) -> list[m.DbObject]:
    o = m.DbObject
    stmt = (
        select(o)
        .where(o.scan_id == scan_id, _contains(o.name, q))
        .order_by(func.length(o.name), func.lower(o.name), o.id)
        .limit(limit)
    )
    return list(s.execute(stmt).scalars().all())


def search_definitions(
    s: Session, scan_id: int, q: str, limit: int, exclude_ids: list[int] | None = None
) -> list[m.DbObject]:
    o = m.DbObject
    stmt = select(o).where(o.scan_id == scan_id, _contains(o.definition, q))
    if exclude_ids:
        stmt = stmt.where(o.id.not_in(exclude_ids))
    stmt = stmt.order_by(func.lower(o.schema_name), func.lower(o.name), o.id).limit(limit)
    return list(s.execute(stmt).scalars().all())


def search_columns(
    s: Session, scan_id: int, q: str, limit: int
) -> list[tuple[m.Column, m.DbObject]]:
    c, o = m.Column, m.DbObject
    stmt = (
        select(c, o)
        .join(o, o.id == c.object_id)
        .where(c.scan_id == scan_id, _contains(c.name, q))
        .order_by(func.length(c.name), func.lower(c.name), func.lower(o.name), c.id)
        .limit(limit)
    )
    return [(col, obj) for col, obj in s.execute(stmt).all()]


# -- stats grids ---------------------------------------------------------------------------


_TABLE_SORTS = {
    "rows": m.TableStats.row_count,
    "data_kb": m.TableStats.data_kb,
    "index_kb": m.TableStats.index_kb,
    "reserved_kb": m.TableStats.reserved_kb,
    "size": m.TableStats.reserved_kb,
    "partitions": m.TableStats.partition_count,
    "name": func.lower(m.DbObject.name),
}
_INDEX_SORTS = {
    "updates": m.IndexUsage.user_updates,
    "seeks": m.IndexUsage.user_seeks,
    "scans": m.IndexUsage.user_scans,
    "lookups": m.IndexUsage.user_lookups,
    "name": func.lower(m.IndexDef.name),
    "table": func.lower(m.DbObject.name),
}
_PROC_SORTS = {
    "exec_count": m.ProcStats.execution_count,
    "total_ms": m.ProcStats.total_elapsed_us,
    "avg_ms": m.ProcStats.avg_elapsed_us,
    "max_ms": m.ProcStats.max_elapsed_us,
    "cpu": m.ProcStats.total_cpu_us,
    "reads": m.ProcStats.total_logical_reads,
    "last_exec": m.ProcStats.last_execution_time,
    "name": func.lower(m.DbObject.name),
}
_MISSING_SORTS = {
    "improvement": m.MissingIndex.improvement_measure,
    "seeks": m.MissingIndex.user_seeks,
    "impact": m.MissingIndex.avg_user_impact,
    "cost": m.MissingIndex.avg_total_user_cost,
    "name": func.lower(m.DbObject.name),
}


def _grid(
    s: Session,
    stmt: Select,
    sort_column,
    order: str,
    limit: int,
    offset: int,
) -> tuple[list[tuple], int]:
    total = _count(s, stmt)
    stmt = _ordered(stmt, sort_column, order).order_by(
        func.lower(m.DbObject.schema_name), func.lower(m.DbObject.name)
    )
    return [tuple(r) for r in s.execute(stmt.limit(limit).offset(offset)).all()], total


def stats_tables(
    s: Session,
    scan_id: int,
    *,
    db: str | None = None,
    schema: str | None = None,
    sort: str = "reserved_kb",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[m.TableStats, m.DbObject]], int]:
    ts, o = m.TableStats, m.DbObject
    stmt = _scope_filters(select(ts, o).join(o, o.id == ts.object_id), scan_id, db, schema).where(
        ts.scan_id == scan_id
    )
    return _grid(s, stmt, _TABLE_SORTS.get(sort, ts.reserved_kb), order, limit, offset)


def stats_indexes(
    s: Session,
    scan_id: int,
    *,
    db: str | None = None,
    schema: str | None = None,
    unused: bool = False,
    sort: str = "updates",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[m.IndexUsage, m.IndexDef, m.DbObject]], int]:
    iu, idx, o = m.IndexUsage, m.IndexDef, m.DbObject
    stmt = select(iu, idx, o).join(idx, idx.id == iu.index_id).join(o, o.id == idx.object_id)
    stmt = _scope_filters(stmt, scan_id, db, schema).where(iu.scan_id == scan_id)
    if unused:
        stmt = stmt.where(iu.is_unused.is_(True))
    return _grid(s, stmt, _INDEX_SORTS.get(sort, iu.user_updates), order, limit, offset)


def stats_procs(
    s: Session,
    scan_id: int,
    *,
    db: str | None = None,
    schema: str | None = None,
    sort: str = "exec_count",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[m.ProcStats, m.DbObject]], int]:
    ps, o = m.ProcStats, m.DbObject
    stmt = _scope_filters(select(ps, o).join(o, o.id == ps.object_id), scan_id, db, schema).where(
        ps.scan_id == scan_id
    )
    return _grid(s, stmt, _PROC_SORTS.get(sort, ps.execution_count), order, limit, offset)


def stats_missing_indexes(
    s: Session,
    scan_id: int,
    *,
    db: str | None = None,
    schema: str | None = None,
    sort: str = "improvement",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[m.MissingIndex, m.DbObject]], int]:
    mi, o = m.MissingIndex, m.DbObject
    stmt = _scope_filters(select(mi, o).join(o, o.id == mi.object_id), scan_id, db, schema).where(
        mi.scan_id == scan_id
    )
    return _grid(s, stmt, _MISSING_SORTS.get(sort, mi.improvement_measure), order, limit, offset)


# -- annotations & tags --------------------------------------------------------------------


def get_annotation(s: Session, target_kind: str, target_key: str) -> m.Annotation | None:
    stmt = select(m.Annotation).where(
        m.Annotation.target_kind == target_kind, m.Annotation.target_key == target_key
    )
    return s.execute(stmt).scalar_one_or_none()


def annotations_for_keys(s: Session, target_kind: str, keys: list[str]) -> dict[str, m.Annotation]:
    if not keys:
        return {}
    rows = s.execute(
        select(m.Annotation).where(
            m.Annotation.target_kind == target_kind, m.Annotation.target_key.in_(keys)
        )
    ).scalars()
    return {a.target_key.casefold(): a for a in rows}


def tags_for_keys(s: Session, target_kind: str, keys: list[str]) -> dict[str, list[str]]:
    if not keys:
        return {}
    stmt = (
        select(m.TagAssignment.target_key, m.Tag.name)
        .join(m.Tag, m.Tag.id == m.TagAssignment.tag_id)
        .where(m.TagAssignment.target_kind == target_kind, m.TagAssignment.target_key.in_(keys))
    )
    out: dict[str, list[str]] = {}
    for key, name in s.execute(stmt):
        out.setdefault(key.casefold(), []).append(name)
    for names in out.values():
        names.sort(key=str.casefold)
    return out


def tag_names_for(s: Session, target_kind: str, target_key: str) -> list[str]:
    return tags_for_keys(s, target_kind, [target_key]).get(target_key.casefold(), [])


def upsert_annotation(
    s: Session,
    target_kind: str,
    target_key: str,
    *,
    description: str | None = UNSET,
    notes: str | None = UNSET,
) -> m.Annotation:
    ann = get_annotation(s, target_kind, target_key)
    if ann is None:
        ann = m.Annotation(target_kind=target_kind, target_key=target_key)
        s.add(ann)
    if description is not UNSET:
        ann.description = description
    if notes is not UNSET:
        ann.notes = notes
    s.flush()
    return ann


def set_tags(s: Session, target_kind: str, target_key: str, names: list[str]) -> list[str]:
    """Replace the tag set of a target; tag names are case-insensitive (first spelling wins)."""
    wanted: dict[str, str] = {}
    for raw in names:
        name = raw.strip()
        if name and name.casefold() not in wanted:
            wanted[name.casefold()] = name
    tags = {t.name.casefold(): t for t in s.execute(select(m.Tag)).scalars()}
    for cf, name in wanted.items():
        if cf not in tags:
            tag = m.Tag(name=name)
            s.add(tag)
            tags[cf] = tag
    s.flush()
    current = {
        tag.name.casefold(): ta
        for ta, tag in s.execute(
            select(m.TagAssignment, m.Tag)
            .join(m.Tag, m.Tag.id == m.TagAssignment.tag_id)
            .where(
                m.TagAssignment.target_kind == target_kind,
                m.TagAssignment.target_key == target_key,
            )
        ).all()
    }
    for cf, ta in current.items():
        if cf not in wanted:
            s.delete(ta)
    for cf in wanted:
        if cf not in current:
            s.add(
                m.TagAssignment(tag_id=tags[cf].id, target_kind=target_kind, target_key=target_key)
            )
    s.flush()
    return sorted((tags[cf].name for cf in wanted), key=str.casefold)


def delete_annotation(s: Session, target_kind: str, target_key: str) -> bool:
    removed = False
    ann = get_annotation(s, target_kind, target_key)
    if ann is not None:
        s.delete(ann)
        removed = True
    result = s.execute(
        delete(m.TagAssignment).where(
            m.TagAssignment.target_kind == target_kind, m.TagAssignment.target_key == target_key
        )
    )
    removed = removed or (result.rowcount or 0) > 0
    s.flush()
    return removed


@dataclass
class AnnotationEntry:
    target_kind: str
    target_key: str
    annotation: m.Annotation | None
    tags: list[str] = field(default_factory=list)


def list_annotations(
    s: Session,
    *,
    connection: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AnnotationEntry], int]:
    entries: dict[tuple[str, str], AnnotationEntry] = {}
    for ann in s.execute(select(m.Annotation)).scalars():
        entries[(ann.target_kind, ann.target_key.casefold())] = AnnotationEntry(
            ann.target_kind, ann.target_key, ann
        )
    stmt = select(m.TagAssignment.target_kind, m.TagAssignment.target_key, m.Tag.name).join(
        m.Tag, m.Tag.id == m.TagAssignment.tag_id
    )
    for kind, key, name in s.execute(stmt):
        entry = entries.setdefault((kind, key.casefold()), AnnotationEntry(kind, key, None))
        entry.tags.append(name)
    rows = list(entries.values())
    for e in rows:
        e.tags.sort(key=str.casefold)
    if connection:
        prefix = connection.casefold() + "|"
        rows = [e for e in rows if e.target_key.casefold().startswith(prefix)]
    if tag:
        wanted = tag.casefold()
        rows = [e for e in rows if any(t.casefold() == wanted for t in e.tags)]
    if q:
        needle = q.casefold()
        rows = [
            e
            for e in rows
            if needle in e.target_key.casefold()
            or (e.annotation is not None and needle in (e.annotation.description or "").casefold())
            or (e.annotation is not None and needle in (e.annotation.notes or "").casefold())
        ]
    rows.sort(key=lambda e: (e.target_key.casefold(), e.target_kind))
    return rows[offset : offset + limit], len(rows)


@dataclass
class TagCount:
    name: str
    color: str | None
    count: int


def list_tags(s: Session, connection: str | None = None) -> list[TagCount]:
    stmt = select(m.TagAssignment.tag_id, func.count())
    if connection:
        prefix = connection.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "|%"
        stmt = stmt.where(func.lower(m.TagAssignment.target_key).like(prefix.lower(), escape="\\"))
    counts = dict(s.execute(stmt.group_by(m.TagAssignment.tag_id)).all())
    tags = s.execute(select(m.Tag).order_by(func.lower(m.Tag.name))).scalars().all()
    return [TagCount(t.name, t.color, int(counts.get(t.id, 0))) for t in tags]


# -- graph loading -------------------------------------------------------------------------


def graph_nodes(s: Session, scan_id: int) -> list[dict[str, Any]]:
    o = m.DbObject
    stmt = (
        select(
            o.id,
            o.database_name,
            o.schema_name,
            o.name,
            o.kind,
            o.scope,
            m.TableStats.row_count,
            m.ProcStats.execution_count,
        )
        .outerjoin(
            m.TableStats, (m.TableStats.object_id == o.id) & (m.TableStats.scan_id == scan_id)
        )
        .outerjoin(m.ProcStats, (m.ProcStats.object_id == o.id) & (m.ProcStats.scan_id == scan_id))
        .where(o.scan_id == scan_id)
    )
    issues = {
        oid
        for (oid,) in s.execute(
            select(m.LineageIssue.object_id).where(m.LineageIssue.scan_id == scan_id).distinct()
        )
    }
    return [
        {
            "id": oid,
            "db": db,
            "schema": schema,
            "name": name,
            "kind": kind,
            "scope": scope,
            "has_lineage_issues": oid in issues,
            "row_count": rows,
            "exec_count": execs,
        }
        for oid, db, schema, name, kind, scope, rows, execs in s.execute(stmt)
    ]


def graph_dependencies(s: Session, scan_id: int) -> list[dict[str, Any]]:
    fk = m.ForeignKeyDef
    fk_names: dict[tuple[int, int], list[str]] = {}
    for parent, referenced, name in s.execute(
        select(fk.parent_object_id, fk.referenced_object_id, fk.name)
        .where(fk.scan_id == scan_id)
        .order_by(fk.name)
    ):
        fk_names.setdefault((parent, referenced), []).append(name)
    d = m.ObjectDependency
    rows = []
    for dep in s.execute(select(d).where(d.scan_id == scan_id).order_by(d.id)).scalars():
        if dep.edge_kind == "fk" and dep.target_object_id is not None:
            names = fk_names.get((dep.source_object_id, dep.target_object_id))
            detail = ", ".join(names) if names else dep.referenced_name
        elif dep.resolution != "resolved":
            detail = dep.referenced_name
        else:
            detail = None
        rows.append(
            {
                "id": dep.id,
                "source": dep.source_object_id,
                "target": dep.target_object_id,
                "kind": dep.edge_kind,
                "resolution": dep.resolution,
                "detail": detail,
            }
        )
    return rows


def column_graph_rows(
    s: Session, scan_id: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, int]]:
    cl = m.ColumnLineage
    edges = [
        {
            "id": str(row.id),
            "source": row.source_column_id,
            "target": row.target_column_id,
            "confidence": row.confidence,
            "transform": row.transform,
            "via_object_id": row.via_object_id,
            "expression": row.expression_sql,
            "statement_kind": row.statement_kind,
        }
        for row in s.execute(
            select(cl)
            .where(cl.scan_id == scan_id, cl.source_column_id.is_not(None))
            .order_by(cl.id)
        ).scalars()
    ]
    ids = {e["source"] for e in edges} | {e["target"] for e in edges}
    columns: list[dict[str, Any]] = []
    if ids:
        c = m.Column
        for cid, oid, name, type_display, ordinal in s.execute(
            select(c.id, c.object_id, c.name, c.type_display, c.ordinal).where(
                c.scan_id == scan_id, c.id.in_(list(ids))
            )
        ):
            columns.append(
                {
                    "id": cid,
                    "object_id": oid,
                    "name": name,
                    "data_type": type_display,
                    "ordinal": ordinal,
                }
            )
    totals = {
        oid: int(n)
        for oid, n in s.execute(
            select(m.Column.object_id, func.count())
            .where(m.Column.scan_id == scan_id)
            .group_by(m.Column.object_id)
        )
    }
    return columns, edges, totals
