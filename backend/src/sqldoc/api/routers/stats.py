"""Stats grids: largest tables, (unused) indexes, hot procs, missing-index suggestions."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from sqldoc.api import build
from sqldoc.api import schemas as S
from sqldoc.api.deps import ScanDep, SessionDep, cache_mutable
from sqldoc.store import repo

router = APIRouter(
    prefix="/scans/{scan_id}/stats", tags=["stats"], dependencies=[Depends(cache_mutable)]
)
Order = Literal["asc", "desc"]


@router.get("/tables", response_model=S.ListEnvelope[S.TableStatsRow])
def tables(
    scan: ScanDep,
    session: SessionDep,
    db: str | None = None,
    schema: str | None = None,
    sort: Literal[
        "rows", "data_kb", "index_kb", "reserved_kb", "size", "partitions", "name"
    ] = "reserved_kb",
    order: Order = "desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> S.ListEnvelope[S.TableStatsRow]:
    rows, total = repo.stats_tables(
        session, scan.id, db=db, schema=schema, sort=sort, order=order, limit=limit, offset=offset
    )
    summaries = build.summary_map(session, scan.id, [o for _, o in rows])
    items = [
        S.TableStatsRow(
            object=summaries[o.id],
            row_count=ts.row_count,
            data_kb=ts.data_kb,
            index_kb=ts.index_kb,
            reserved_kb=ts.reserved_kb,
            partition_count=ts.partition_count,
            is_heap=ts.is_heap,
            compression=ts.compression,
        )
        for ts, o in rows
    ]
    return S.ListEnvelope(items=items, total=total, limit=limit, offset=offset)


@router.get("/indexes", response_model=S.ListEnvelope[S.IndexStatsRow])
def indexes(
    scan: ScanDep,
    session: SessionDep,
    db: str | None = None,
    schema: str | None = None,
    unused: bool = False,
    sort: Literal["updates", "seeks", "scans", "lookups", "name", "table"] = "updates",
    order: Order = "desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> S.ListEnvelope[S.IndexStatsRow]:
    rows, total = repo.stats_indexes(
        session,
        scan.id,
        db=db,
        schema=schema,
        unused=unused,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    summaries = build.summary_map(session, scan.id, [o for _, _, o in rows])
    index_cols = repo.index_columns_for(session, scan.id, [idx.id for _, idx, _ in rows])
    items = []
    for u, idx, o in rows:
        cols = index_cols.get(idx.id, [])
        items.append(
            S.IndexStatsRow(
                object=summaries[o.id],
                index_id=idx.id,
                index_name=idx.name,
                type_desc=idx.type_desc,
                is_unique=idx.is_unique,
                is_primary_key=idx.is_primary_key,
                is_unique_constraint=idx.is_unique_constraint,
                key_columns=[c.column_name for c in cols if not c.is_included],
                included_columns=[c.column_name for c in cols if c.is_included],
                seeks=u.user_seeks,
                scans=u.user_scans,
                lookups=u.user_lookups,
                updates=u.user_updates,
                last_seek=u.last_user_seek,
                last_scan=u.last_user_scan,
                last_lookup=u.last_user_lookup,
                last_update=u.last_user_update,
                is_unused=bool(u.is_unused),
            )
        )
    return S.ListEnvelope(items=items, total=total, limit=limit, offset=offset)


@router.get("/procs", response_model=S.ListEnvelope[S.ProcStatsRow])
def procs(
    scan: ScanDep,
    session: SessionDep,
    db: str | None = None,
    schema: str | None = None,
    sort: Literal[
        "exec_count", "total_ms", "avg_ms", "max_ms", "cpu", "reads", "last_exec", "name"
    ] = "exec_count",
    order: Order = "desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> S.ListEnvelope[S.ProcStatsRow]:
    rows, total = repo.stats_procs(
        session, scan.id, db=db, schema=schema, sort=sort, order=order, limit=limit, offset=offset
    )
    summaries = build.summary_map(session, scan.id, [o for _, o in rows])
    items = [
        S.ProcStatsRow(
            object=summaries[o.id],
            exec_count=ps.execution_count,
            total_ms=build.us_to_ms(ps.total_elapsed_us),
            avg_ms=build.us_to_ms(ps.avg_elapsed_us),
            min_ms=build.us_to_ms(ps.min_elapsed_us),
            max_ms=build.us_to_ms(ps.max_elapsed_us),
            total_cpu_ms=build.us_to_ms(ps.total_cpu_us),
            total_logical_reads=ps.total_logical_reads,
            last_exec_at=ps.last_execution_time,
            cached_since=ps.cached_time,
        )
        for ps, o in rows
    ]
    return S.ListEnvelope(items=items, total=total, limit=limit, offset=offset)


@router.get("/missing-indexes", response_model=S.ListEnvelope[S.MissingIndexRow])
def missing_indexes(
    scan: ScanDep,
    session: SessionDep,
    db: str | None = None,
    schema: str | None = None,
    sort: Literal["improvement", "seeks", "impact", "cost", "name"] = "improvement",
    order: Order = "desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> S.ListEnvelope[S.MissingIndexRow]:
    rows, total = repo.stats_missing_indexes(
        session, scan.id, db=db, schema=schema, sort=sort, order=order, limit=limit, offset=offset
    )
    summaries = build.summary_map(session, scan.id, [o for _, o in rows])
    items = [
        S.MissingIndexRow(object=summaries[o.id], **build.missing_index_out(mi)) for mi, o in rows
    ]
    return S.ListEnvelope(items=items, total=total, limit=limit, offset=offset)
