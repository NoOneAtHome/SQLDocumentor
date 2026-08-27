"""Catalog browsing: object listing, composite detail, name lookup, definition, search."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from sqldoc.api import build
from sqldoc.api import schemas as S
from sqldoc.api.deps import RuntimeDep, ScanDep, SessionDep, cache_mutable, cache_snapshot, csv_set
from sqldoc.store import models as m
from sqldoc.store import repo

router = APIRouter(prefix="/scans/{scan_id}", tags=["catalog"])

SortKey = Literal["name", "kind", "schema", "rows", "size", "execs", "modified"]
Order = Literal["asc", "desc"]


def _object_or_404(session, scan: m.Scan, object_id: int) -> m.DbObject:
    obj = repo.get_object(session, scan.id, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"object {object_id} not in scan {scan.id}")
    return obj


@router.get(
    "/objects",
    response_model=S.ListEnvelope[S.ObjectSummary],
    dependencies=[Depends(cache_mutable)],
)
def list_objects(
    scan: ScanDep,
    session: SessionDep,
    db: str | None = None,
    schema: str | None = None,
    kind: str | None = Query(None, description="comma separated object kinds"),
    scope: str | None = Query(None, description="comma separated: in_scope,cascaded,external"),
    q: str | None = None,
    tag: str | None = None,
    has_issues: bool | None = None,
    sort: SortKey = "name",
    order: Order = "asc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> S.ListEnvelope[S.ObjectSummary]:
    f = repo.ObjectFilter(
        db=db,
        schema=schema,
        kind=kind,
        scope=scope,
        q=q,
        tag=tag,
        has_issues=has_issues,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    objs, total = repo.list_objects(session, scan.id, f)
    return S.ListEnvelope(
        items=build.object_summaries(session, scan.id, objs),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/objects/lookup", response_model=S.ObjectDetail, dependencies=[Depends(cache_mutable)])
def lookup_object(
    scan: ScanDep, rt: RuntimeDep, session: SessionDep, db: str, schema: str, name: str
) -> S.ObjectDetail:
    obj = repo.lookup_object(session, scan.id, db, schema, name)
    if obj is None:
        raise HTTPException(
            status_code=404, detail=f"{db}.{schema}.{name} not found in scan {scan.id}"
        )
    return build.object_detail(session, rt.db, scan, obj)


@router.get(
    "/objects/{object_id}", response_model=S.ObjectDetail, dependencies=[Depends(cache_mutable)]
)
def get_object(
    scan: ScanDep, rt: RuntimeDep, session: SessionDep, object_id: int
) -> S.ObjectDetail:
    return build.object_detail(session, rt.db, scan, _object_or_404(session, scan, object_id))


@router.get(
    "/objects/{object_id}/definition",
    response_model=S.Definition,
    dependencies=[Depends(cache_snapshot)],
)
def get_definition(scan: ScanDep, session: SessionDep, object_id: int) -> S.Definition:
    obj = _object_or_404(session, scan, object_id)
    return S.Definition(
        definition=obj.definition,
        length=len(obj.definition or ""),
        has_dynamic_sql=bool(obj.has_dynamic_sql),
    )


def _snippet(text: str | None, needle: str, width: int = 60) -> str | None:
    if not text:
        return None
    pos = text.casefold().find(needle.casefold())
    if pos < 0:
        return text[: width * 2]
    start, end = max(0, pos - width), min(len(text), pos + len(needle) + width)
    return ("..." if start else "") + text[start:end] + ("..." if end < len(text) else "")


@router.get("/search", response_model=S.SearchResult, dependencies=[Depends(cache_mutable)])
def search(
    scan: ScanDep,
    session: SessionDep,
    q: str = Query(min_length=1),
    kinds: str | None = Query(None, description="comma separated: object,column,definition"),
    limit: int = Query(20, ge=1, le=200),
) -> S.SearchResult:
    wanted = csv_set(kinds) or frozenset({"object", "column"})
    objects: list[S.SearchObjectHit] = []
    if "object" in wanted:
        hits = repo.search_objects(session, scan.id, q, limit)
        for summary, obj in zip(build.object_summaries(session, scan.id, hits), hits, strict=True):
            objects.append(
                S.SearchObjectHit(
                    **summary.model_dump(by_alias=True),
                    match=S.SearchMatch(field="name", snippet=obj.name),
                )
            )
    if "definition" in wanted and len(objects) < limit:
        hits = repo.search_definitions(
            session, scan.id, q, limit - len(objects), exclude_ids=[o.id for o in objects]
        )
        for summary, obj in zip(build.object_summaries(session, scan.id, hits), hits, strict=True):
            objects.append(
                S.SearchObjectHit(
                    **summary.model_dump(by_alias=True),
                    match=S.SearchMatch(field="definition", snippet=_snippet(obj.definition, q)),
                )
            )
    columns: list[S.SearchColumnHit] = []
    if "column" in wanted:
        rows = repo.search_columns(session, scan.id, q, limit)
        summaries = build.summary_map(session, scan.id, [o for _, o in rows])
        columns = [
            S.SearchColumnHit(object=summaries[o.id], column=c.name, data_type=c.type_display)
            for c, o in rows
        ]
    return S.SearchResult(objects=objects, columns=columns)
