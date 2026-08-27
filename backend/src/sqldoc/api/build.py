"""Compose API response models from repo rows and graph results.

Shape knowledge (what goes into ``ObjectSummary``, ``ObjectDetail``, the lineage
graphs ...) lives here; SQL lives in :mod:`sqldoc.store.repo`.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from sqldoc.api import schemas as S
from sqldoc.graph import traverse
from sqldoc.graph.traverse import ColumnEgoResult, ColumnGraph, EgoResult, ScanGraph
from sqldoc.store import models as m
from sqldoc.store import repo
from sqldoc.store.db import Database


def us_to_ms(us: int | None) -> float | None:
    return None if us is None else us / 1000


# -- scans -------------------------------------------------------------------------------


def scan_summary(scan: m.Scan, snap: dict[str, Any] | None = None) -> S.ScanSummary:
    status = snap["status"] if snap else scan.status
    finished = (snap.get("finished_at") if snap else None) or scan.finished_at
    error = (snap.get("error") if snap else None) or scan.error
    counts = json.loads(scan.summary_json) if scan.summary_json else None
    options = json.loads(scan.options_json) if scan.options_json else None
    duration = int((finished - scan.started_at).total_seconds() * 1000) if finished else None
    return S.ScanSummary(
        id=scan.id,
        connection=scan.connection_name,
        status=status,
        started_at=scan.started_at,
        finished_at=finished,
        duration_ms=duration,
        options=S.ScanOptionsOut(**options) if options else None,
        counts=S.ScanCounts(**{k: v for k, v in counts.items() if k in S.ScanCounts.model_fields})
        if counts
        else None,
        error=error,
        server_name=scan.server_name,
        server_version=scan.server_version,
        server_edition=scan.server_edition,
        auth_scheme=scan.auth_scheme,
        driver=scan.driver,
    )


def scan_status(scan: m.Scan, snap: dict[str, Any]) -> S.ScanStatus:
    base = scan_summary(scan, snap)
    progress = S.ScanProgressInfo(
        phase=snap.get("phase"),
        phase_index=snap.get("phase_index") or 0,
        phase_count=snap.get("phase_count") or 7,
        current=snap.get("current") or 0,
        total=snap.get("total") or 0,
        message=snap.get("message") or "",
        updated_at=snap.get("updated_at"),
    )
    return S.ScanStatus(
        **base.model_dump(),
        progress=progress,
        warnings=[S.ScanWarningOut(**w) for w in snap.get("warnings", [])],
        log=[S.ScanLogEntry(**entry) for entry in snap.get("log", [])],
    )


def scan_overview(data: dict[str, Any]) -> S.ScanOverview:
    return S.ScanOverview(
        databases=[S.DatabaseOverview(**d) for d in data["databases"]],
        counts=S.ScanCounts(**data["counts"]),
        lineage_coverage=data["lineage_coverage"],
        warnings_summary=S.WarningsSummary(**data["warnings_summary"]),
        warnings=[
            S.ScanWarningOut(
                phase=w.phase, code=w.code, message=w.message, database=w.database_name
            )
            for w in data["warnings"]
        ],
    )


# -- objects -----------------------------------------------------------------------------


def object_ref(o: m.DbObject) -> S.ObjectRef:
    return S.ObjectRef(id=o.id, db=o.database_name, schema=o.schema_name, name=o.name, kind=o.kind)


def object_summaries(
    session: Session, scan_id: int, objs: list[m.DbObject]
) -> list[S.ObjectSummary]:
    extras = repo.summary_extras(session, scan_id, [o.id for o in objs])
    keys = [o.object_key for o in objs]
    anns = repo.annotations_for_keys(session, "object", keys)
    tags = repo.tags_for_keys(session, "object", keys)
    out: list[S.ObjectSummary] = []
    for o in objs:
        x = extras[o.id]
        ann = anns.get(o.object_key.casefold())
        out.append(
            S.ObjectSummary(
                id=o.id,
                object_key=o.object_key,
                db=o.database_name,
                schema=o.schema_name,
                name=o.name,
                kind=o.kind,
                scope=o.scope,
                description=o.description,
                annotation_description=ann.description if ann else None,
                tags=tags.get(o.object_key.casefold(), []),
                row_count=x["row_count"],
                total_size_kb=x["total_size_kb"],
                exec_count=x["exec_count"],
                modified_at=o.modify_date,
                lineage_status=o.lineage_status,
                has_lineage_issues=x["has_lineage_issues"],
            )
        )
    return out


def summary_map(
    session: Session, scan_id: int, objs: list[m.DbObject]
) -> dict[int, S.ObjectSummary]:
    unique = list({o.id: o for o in objs}.values())
    return {s.id: s for s in object_summaries(session, scan_id, unique)}


# -- annotations -------------------------------------------------------------------------


def parse_target_key(key: str) -> dict[str, str | None]:
    parts = key.split("|")
    out: dict[str, str | None] = {
        "connection": None,
        "db": None,
        "schema": None,
        "name": parts[-1],
        "column": None,
    }
    if parts[0] == "external" or len(parts) < 4:
        return out
    out["connection"], out["db"], out["schema"], out["name"] = parts[:4]
    out["column"] = "|".join(parts[4:]) or None
    return out


def annotation_out(kind: str, key: str, ann: m.Annotation | None, tags: list[str]) -> S.Annotation:
    return S.Annotation(
        target_kind=kind,
        target_key=key,
        **parse_target_key(key),
        description=ann.description if ann else None,
        notes=ann.notes if ann else None,
        tags=tags,
        created_at=ann.created_at if ann else None,
        updated_at=ann.updated_at if ann else None,
    )


# -- object detail -----------------------------------------------------------------------


def _index_out(info: repo.IndexInfo) -> S.Index:
    idx, u = info.index, info.usage
    usage = (
        S.IndexUsage(
            seeks=u.user_seeks,
            scans=u.user_scans,
            lookups=u.user_lookups,
            updates=u.user_updates,
            last_seek=u.last_user_seek,
            last_scan=u.last_user_scan,
            last_lookup=u.last_user_lookup,
            last_update=u.last_user_update,
        )
        if u
        else None
    )
    return S.Index(
        id=idx.id,
        name=idx.name,
        type_desc=idx.type_desc,
        is_unique=idx.is_unique,
        is_primary_key=idx.is_primary_key,
        is_unique_constraint=idx.is_unique_constraint,
        key_columns=[
            S.IndexKeyColumn(name=ic.column_name, desc=bool(ic.is_descending))
            for ic in info.columns
            if not ic.is_included
        ],
        included_columns=[ic.column_name for ic in info.columns if ic.is_included],
        filter=idx.filter_definition,
        is_disabled=idx.is_disabled,
        usage=usage,
        is_unused=bool(u.is_unused) if u else False,
        description=idx.description,
    )


def _key_constraint(info: repo.IndexInfo) -> S.KeyConstraint:
    return S.KeyConstraint(
        name=info.index.name,
        type_desc=info.index.type_desc,
        columns=[ic.column_name for ic in info.columns if not ic.is_included],
    )


def _fk_ref(f: repo.ForeignKeyInfo) -> S.ForeignKeyRef:
    return S.ForeignKeyRef(
        id=f.fk.id,
        name=f.fk.name,
        parent=object_ref(f.parent),
        referenced=object_ref(f.referenced),
        columns=[
            S.ForeignKeyColumnPair(
                column=c.parent_column_name, referenced_column=c.referenced_column_name
            )
            for c in f.columns
        ],
        delete_action=f.fk.delete_action,
        update_action=f.fk.update_action,
        is_disabled=f.fk.is_disabled,
        is_not_trusted=f.fk.is_not_trusted,
    )


def _dep_ref(info: repo.DependencyInfo, other: m.DbObject | None) -> S.DepRef:
    dep = info.dep
    if other is None:
        return S.DepRef(
            name=dep.referenced_name or "?",
            edge_kind=dep.edge_kind,
            resolution=dep.resolution,
            referenced_name=dep.referenced_name,
        )
    return S.DepRef(
        object_id=other.id,
        db=other.database_name,
        schema=other.schema_name,
        name=other.name,
        kind=other.kind,
        scope=other.scope,
        edge_kind=dep.edge_kind,
        resolution=dep.resolution,
        referenced_name=dep.referenced_name,
    )


def _stats(session: Session, scan: m.Scan, obj: m.DbObject) -> S.TableStats | S.ExecStats | None:
    if obj.kind in repo.TABLE_KINDS:
        ts = repo.table_stats_for(session, scan.id, obj.id)
        if ts is None:
            return None
        return S.TableStats(
            row_count=ts.row_count,
            data_kb=ts.data_kb,
            index_kb=ts.index_kb,
            reserved_kb=ts.reserved_kb,
            partition_count=ts.partition_count,
            is_heap=ts.is_heap,
            compression=ts.compression,
            stats_as_of=scan.finished_at or scan.started_at,
        )
    if obj.kind in repo.EXEC_KINDS:
        ps = repo.proc_stats_for(session, scan.id, obj.id)
        if ps is None:
            return None
        return S.ExecStats(
            exec_count=ps.execution_count,
            total_ms=us_to_ms(ps.total_elapsed_us),
            avg_ms=us_to_ms(ps.avg_elapsed_us),
            min_ms=us_to_ms(ps.min_elapsed_us),
            max_ms=us_to_ms(ps.max_elapsed_us),
            total_cpu_ms=us_to_ms(ps.total_cpu_us),
            total_logical_reads=ps.total_logical_reads,
            last_exec_at=ps.last_execution_time,
            cached_since=ps.cached_time,
            since_server_start=scan.server_start_time,
        )
    return None


def missing_index_out(mi: m.MissingIndex) -> dict[str, Any]:
    return dict(
        id=mi.id,
        equality_columns=mi.equality_columns,
        inequality_columns=mi.inequality_columns,
        included_columns=mi.included_columns,
        user_seeks=mi.user_seeks,
        user_scans=mi.user_scans,
        last_user_seek=mi.last_user_seek,
        avg_cost=mi.avg_total_user_cost,
        avg_impact=mi.avg_user_impact,
        improvement_measure=mi.improvement_measure,
        suggested_ddl=mi.suggested_ddl,
    )


def object_detail(session: Session, db: Database, scan: m.Scan, obj: m.DbObject) -> S.ObjectDetail:
    sid = scan.id
    summary = object_summaries(session, sid, [obj])[0]
    cols = repo.columns_for(session, sid, obj.id)
    indexes = repo.indexes_for(session, sid, obj.id)
    fks_out = repo.foreign_keys_for(session, sid, obj.id, "out")
    fks_in = repo.foreign_keys_for(session, sid, obj.id, "in")
    checks = repo.check_constraints_for(session, sid, obj.id)
    col_names = {c.id: c.name for c in cols}

    pk = next((i for i in indexes if i.index.is_primary_key), None)
    pk_cols = (
        {ic.column_name.casefold() for ic in pk.columns if not ic.is_included} if pk else set()
    )
    fk_to: dict[str, S.FkTarget] = {}
    for f in fks_out:
        for fkc in f.columns:
            fk_to.setdefault(
                fkc.parent_column_name.casefold(),
                S.FkTarget(
                    object_id=f.referenced.id,
                    schema=f.referenced.schema_name,
                    name=f.referenced.name,
                    column=fkc.referenced_column_name,
                ),
            )
    lineage = repo.column_lineage_counts(session, sid, obj.id)
    col_keys = [c.column_key for c in cols]
    col_anns = repo.annotations_for_keys(session, "column", col_keys)
    col_tags = repo.tags_for_keys(session, "column", col_keys)
    columns: list[S.Column] = []
    column_annotations: dict[str, S.Annotation] = {}
    for c in cols:
        ann = col_anns.get(c.column_key.casefold())
        tags = col_tags.get(c.column_key.casefold(), [])
        up, down = lineage.get(c.id, (0, 0))
        columns.append(
            S.Column(
                id=c.id,
                ordinal=c.ordinal,
                name=c.name,
                column_kind=c.column_kind,
                type_display=c.type_display,
                is_nullable=c.is_nullable,
                is_identity=c.is_identity,
                is_computed=c.is_computed,
                computed_definition=c.computed_definition,
                default_definition=c.default_definition,
                collation=c.collation_name,
                in_primary_key=c.name.casefold() in pk_cols,
                fk_to=fk_to.get(c.name.casefold()),
                ms_description=c.description,
                description=ann.description if ann else None,
                lineage=S.ColumnLineageCounts(upstream=up, downstream=down),
            )
        )
        if ann is not None or tags:
            column_annotations[c.name] = annotation_out("column", c.column_key, ann, tags)

    parameters = [
        S.Parameter(
            id=p.id,
            parameter_id=p.parameter_id,
            name=p.name,
            type_display=p.type_display,
            is_output=p.is_output,
            has_default_value=p.has_default_value,
            default_value=p.default_value,
            is_readonly=p.is_readonly,
            is_table_type=p.is_table_type,
            is_return_value=bool(p.is_return_value),
            description=p.description,
        )
        for p in repo.parameters_for(session, sid, obj.id)
    ]
    keys = S.ObjectKeys(
        primary_key=_key_constraint(pk) if pk else None,
        unique_constraints=[_key_constraint(i) for i in indexes if i.index.is_unique_constraint],
        foreign_keys_out=[_fk_ref(f) for f in fks_out],
        foreign_keys_in=[_fk_ref(f) for f in fks_in],
        check_constraints=[
            S.CheckConstraint(
                id=ck.id,
                name=ck.name,
                column=col_names.get(ck.column_id) if ck.column_id else None,
                definition=ck.definition,
                is_disabled=ck.is_disabled,
                is_not_trusted=ck.is_not_trusted,
            )
            for ck in checks
        ],
    )
    triggers = [
        S.TriggerRef(
            id=t.id,
            name=t.name,
            events=t.trigger_events,
            is_instead_of=t.is_instead_of_trigger,
            is_disabled=t.is_disabled,
        )
        for t in repo.triggers_for(session, sid, obj.id)
    ]
    uses, used_by = repo.dependencies_for(session, sid, obj.id)
    graph = traverse.load_graph(db, sid)
    parent = session.get(m.DbObject, obj.parent_object_id) if obj.parent_object_id else None
    ann = repo.get_annotation(session, "object", obj.object_key)
    obj_tags = repo.tag_names_for(session, "object", obj.object_key)
    return S.ObjectDetail(
        summary=summary,
        sql_object_id=obj.sql_object_id,
        ms_description=obj.description,
        created_at=obj.create_date,
        modified_at=obj.modify_date,
        parent=S.ParentRef(
            id=parent.id, schema=parent.schema_name, name=parent.name, kind=parent.kind
        )
        if parent
        else None,
        definition_length=len(obj.definition or ""),
        has_dynamic_sql=bool(obj.has_dynamic_sql),
        is_schema_bound=obj.is_schema_bound,
        trigger_events=obj.trigger_events,
        is_instead_of_trigger=obj.is_instead_of_trigger,
        is_disabled=obj.is_disabled,
        external_server=obj.external_server,
        columns=columns,
        parameters=parameters,
        indexes=[_index_out(i) for i in indexes],
        keys=keys,
        triggers=triggers,
        stats=_stats(session, scan, obj),
        missing_indexes=[
            S.MissingIndex(**missing_index_out(mi))
            for mi in repo.missing_indexes_for(session, sid, obj.id)
        ],
        dependencies=S.Dependencies(
            uses=[_dep_ref(i, i.target) for i in uses],
            used_by=[_dep_ref(i, i.source) for i in used_by],
        ),
        lineage_counts=S.LineageCounts(
            upstream=len(graph.predecessors(obj.id)),
            downstream=len(graph.successors(obj.id)),
            columns_with_lineage=sum(1 for c in cols if lineage.get(c.id, (0, 0)) != (0, 0)),
        ),
        lineage_issues=[
            S.LineageIssue(
                kind=i.kind, statement_index=i.statement_index, message=i.message, snippet=i.snippet
            )
            for i in repo.lineage_issues_for(session, sid, obj.id)
        ],
        annotation=annotation_out("object", obj.object_key, ann, obj_tags)
        if ann is not None or obj_tags
        else None,
        column_annotations=column_annotations,
    )


# -- lineage graphs ----------------------------------------------------------------------


def lineage_graph(graph: ScanGraph, res: EgoResult) -> S.LineageGraph:
    ordered = sorted(res.hops.items(), key=lambda kv: (kv[1], graph.nodes[kv[0]].name.casefold()))
    nodes = []
    for nid, hop in ordered:
        n = graph.nodes[nid]
        up, down = res.more.get(nid, (0, 0))
        nodes.append(
            S.LineageNode(
                id=f"o:{nid}",
                object_id=nid,
                db=n.db,
                schema=n.schema,
                name=n.name,
                kind=n.kind,
                scope=n.scope,
                hop=hop,
                row_count=n.row_count,
                exec_count=n.exec_count,
                has_lineage_issues=n.has_lineage_issues,
                more=S.LineageMore(upstream=up, downstream=down),
            )
        )
    edges = [
        S.LineageEdge(
            id=f"e:{e.id}",
            source=f"o:{e.source}",
            target=f"o:{e.target}",
            kind=e.kind,
            resolution=e.resolution,
            detail=e.detail,
        )
        for e in res.edges
    ]
    return S.LineageGraph(
        focus=f"o:{res.focus}", nodes=nodes, edges=edges, truncated=res.truncated, total=res.total
    )


def column_lineage_graph(
    graph: ScanGraph, cg: ColumnGraph, res: ColumnEgoResult, focus_column: str | None
) -> S.ColumnLineageGraph:
    ordered = sorted(
        (kv for kv in res.hops.items() if kv[0] in graph.nodes),
        key=lambda kv: (kv[1], graph.nodes[kv[0]].name.casefold()),
    )
    nodes = []
    for oid, hop in ordered:
        n = graph.nodes[oid]
        up, down = res.more.get(oid, (0, 0))
        nodes.append(
            S.ColumnLineageNode(
                id=f"o:{oid}",
                object_id=oid,
                db=n.db,
                schema=n.schema,
                name=n.name,
                kind=n.kind,
                scope=n.scope,
                hop=hop,
                has_lineage_issues=n.has_lineage_issues,
                more=S.LineageMore(upstream=up, downstream=down),
                columns=[
                    S.ColumnLineageNodeColumn(
                        column_id=cid,
                        name=cg.columns[cid].name,
                        data_type=cg.columns[cid].data_type,
                    )
                    for cid in res.columns.get(oid, [])
                ],
                column_count_total=cg.column_totals.get(oid, 0),
            )
        )
    edges = []
    for e in res.edges:
        src, tgt = cg.columns[e.source], cg.columns[e.target]
        via = graph.nodes.get(e.via_object_id) if e.via_object_id is not None else None
        edges.append(
            S.ColumnLineageEdge(
                id=f"c:{e.id}",
                source=f"o:{src.object_id}",
                source_column=src.name,
                target=f"o:{tgt.object_id}",
                target_column=tgt.name,
                confidence=e.confidence,
                transform=e.transform,
                via_object_id=e.via_object_id,
                via_name=via.qualified_name if via else None,
                expression=e.expression,
            )
        )
    return S.ColumnLineageGraph(
        focus=S.ColumnLineageFocus(object_id=res.focus, column=focus_column),
        nodes=nodes,
        edges=edges,
        truncated=res.truncated,
        total=res.total,
    )
