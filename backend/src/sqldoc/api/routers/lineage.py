"""Lineage: object ego graph, column graph, per-object column counts, summary, issues.

Graph semantics (data-flow direction, upstream/downstream) are documented in
:mod:`sqldoc.graph.traverse`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from sqldoc.api import build
from sqldoc.api import schemas as S
from sqldoc.api.deps import RuntimeDep, ScanDep, SessionDep, cache_snapshot, csv_set
from sqldoc.graph import traverse
from sqldoc.graph.traverse import EgoOptions
from sqldoc.store import repo

router = APIRouter(
    prefix="/scans/{scan_id}/lineage", tags=["lineage"], dependencies=[Depends(cache_snapshot)]
)

Direction = Literal["up", "down", "both"]


@router.get("/objects", response_model=S.LineageGraph)
def object_graph(
    scan: ScanDep,
    rt: RuntimeDep,
    focus: int = Query(description="object id"),
    direction: Direction = "both",
    depth: int = Query(2, ge=1, le=5),
    kinds: str | None = Query(None, description="comma separated object kinds to include"),
    schemas: str | None = Query(None, description="comma separated schema names to include"),
    edge_kinds: str | None = Query(None, description="comma separated edge kinds to follow"),
    include_cascaded: bool = True,
    include_external: bool = True,
    max_nodes: int = Query(200, ge=1, le=1000),
) -> S.LineageGraph:
    graph = traverse.load_graph(rt.db, scan.id)
    if focus not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"object {focus} not in scan {scan.id}")
    res = traverse.ego_graph(
        graph,
        focus,
        EgoOptions(
            direction=direction,
            depth=depth,
            kinds=csv_set(kinds),
            schemas=csv_set(schemas),
            edge_kinds=csv_set(edge_kinds),
            include_cascaded=include_cascaded,
            include_external=include_external,
            max_nodes=max_nodes,
        ),
    )
    return build.lineage_graph(graph, res)


@router.get("/columns", response_model=S.ColumnLineageGraph)
def column_graph(
    scan: ScanDep,
    rt: RuntimeDep,
    session: SessionDep,
    focus: int = Query(description="object id"),
    column: str | None = Query(None, description="seed column; omit for all lineage-bearing"),
    direction: Direction = "both",
    depth: int = Query(2, ge=1, le=5),
    min_confidence: Literal["unresolved", "inferred", "exact"] = "unresolved",
    collapse_temp: bool = False,
    max_nodes: int = Query(150, ge=1, le=1000),
) -> S.ColumnLineageGraph:
    graph = traverse.load_graph(rt.db, scan.id)
    if focus not in graph.nodes:
        raise HTTPException(status_code=404, detail=f"object {focus} not in scan {scan.id}")
    cg = traverse.load_column_graph(rt.db, scan.id)
    if collapse_temp:
        cg = cg.collapsed()
    focus_column: str | None = None
    if column is not None:
        col = repo.column_by_name(session, scan.id, focus, column)
        if col is None:
            raise HTTPException(status_code=404, detail=f"column {column!r} not on object {focus}")
        focus_column = col.name
        seeds = [col.id]
    else:
        seeds = cg.object_columns(focus)
    res = traverse.column_ego(
        cg,
        focus,
        seeds,
        direction=direction,
        depth=depth,
        min_confidence=min_confidence,
        max_nodes=max_nodes,
    )
    return build.column_lineage_graph(graph, cg, res, focus_column)


@router.get("/objects/{object_id}/columns", response_model=list[S.ObjectColumnLineage])
def object_columns(
    scan: ScanDep, session: SessionDep, object_id: int
) -> list[S.ObjectColumnLineage]:
    if repo.get_object(session, scan.id, object_id) is None:
        raise HTTPException(status_code=404, detail=f"object {object_id} not in scan {scan.id}")
    counts = repo.column_lineage_counts(session, scan.id, object_id)
    confidences = repo.column_lineage_confidences(session, scan.id, object_id)
    out = []
    for c in repo.columns_for(session, scan.id, object_id):
        up, down = counts.get(c.id, (0, 0))
        conf = confidences.get(c.id, {})
        out.append(
            S.ObjectColumnLineage(
                column_id=c.id,
                name=c.name,
                upstream_count=up,
                downstream_count=down,
                confidences=S.ConfidenceCounts(
                    exact=conf.get("exact", 0),
                    inferred=conf.get("inferred", 0),
                    unresolved=conf.get("unresolved", 0),
                ),
            )
        )
    return out


@router.get("/summary", response_model=S.LineageSummary)
def lineage_summary(scan: ScanDep, rt: RuntimeDep, session: SessionDep) -> S.LineageSummary:
    data = repo.lineage_summary(session, scan.id)
    graph = traverse.load_graph(rt.db, scan.id)
    ranked = sorted(
        (n for n in graph.nodes.values() if graph.degree(n.id) > 0),
        key=lambda n: (-graph.degree(n.id), n.name.casefold(), n.id),
    )
    hubs = [
        S.LineageHub(
            object_id=n.id,
            db=n.db,
            schema=n.schema,
            name=n.name,
            kind=n.kind,
            upstream=len(graph.predecessors(n.id)),
            downstream=len(graph.successors(n.id)),
            degree=graph.degree(n.id),
        )
        for n in ranked[:10]
    ]
    return S.LineageSummary(**data, top_hubs=hubs)


@router.get("/issues", response_model=S.ListEnvelope[S.LineageIssueItem])
def lineage_issues(
    scan: ScanDep,
    session: SessionDep,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> S.ListEnvelope[S.LineageIssueItem]:
    rows, total = repo.lineage_issues(session, scan.id, limit, offset)
    items = [
        S.LineageIssueItem(
            id=issue.id,
            object=build.object_ref(obj),
            kind=issue.kind,
            statement_index=issue.statement_index,
            message=issue.message,
            snippet=issue.snippet,
        )
        for issue, obj in rows
    ]
    return S.ListEnvelope(items=items, total=total, limit=limit, offset=offset)
