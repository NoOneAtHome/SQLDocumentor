"""Scan lifecycle: list/start per connection; status, cancel, delete, summary per scan."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from sqldoc.api import build
from sqldoc.api import schemas as S
from sqldoc.api.deps import TERMINAL, RuntimeDep, ScanDep, SessionDep
from sqldoc.api.routers.connections import connection_or_404
from sqldoc.graph import traverse
from sqldoc.scan.manager import ScanAlreadyRunning
from sqldoc.store import repo

router = APIRouter(tags=["scans"])


@router.get("/connections/{name}/scans", response_model=S.ListEnvelope[S.ScanSummary])
def list_scans(
    name: str,
    rt: RuntimeDep,
    session: SessionDep,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> S.ListEnvelope[S.ScanSummary]:
    cfg = connection_or_404(rt, name)
    scans, total = repo.list_scans(session, cfg.name, limit, offset)
    return S.ListEnvelope(
        items=[build.scan_summary(s) for s in scans], total=total, limit=limit, offset=offset
    )


@router.post("/connections/{name}/scans", response_model=S.ScanStarted, status_code=202)
def start_scan(name: str, rt: RuntimeDep, body: S.ScanStartRequest | None = None) -> S.ScanStarted:
    cfg = connection_or_404(rt, name)
    overrides = {k: v for k, v in (body.model_dump() if body else {}).items() if v is not None}
    options = rt.cfg.scan.model_copy(update=overrides) if overrides else None
    try:
        scan_id = rt.manager.start(cfg.name, options)
    except ScanAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return S.ScanStarted(scan_id=scan_id)


@router.get("/scans/{scan_id}", response_model=S.ScanStatus)
def get_scan(scan: ScanDep, rt: RuntimeDep) -> S.ScanStatus:
    snap = rt.manager.progress(scan.id)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"scan {scan.id} not found")
    return build.scan_status(scan, snap)


@router.post("/scans/{scan_id}/cancel", response_model=S.ScanCancelled)
def cancel_scan(scan: ScanDep, rt: RuntimeDep) -> S.ScanCancelled:
    return S.ScanCancelled(scan_id=scan.id, cancelled=rt.manager.cancel(scan.id))


@router.delete("/scans/{scan_id}", status_code=204, response_class=Response)
def delete_scan(scan: ScanDep, rt: RuntimeDep, session: SessionDep) -> Response:
    if rt.manager.running_for(scan.connection_name) == scan.id:
        raise HTTPException(status_code=409, detail=f"scan {scan.id} is still running")
    repo.delete_scan(session, scan.id)
    session.commit()
    traverse.invalidate()
    return Response(status_code=204)


@router.get("/scans/{scan_id}/summary", response_model=S.ScanOverview)
def scan_summary(scan: ScanDep, session: SessionDep, response: Response) -> S.ScanOverview:
    if scan.status in TERMINAL:
        response.headers["Cache-Control"] = "max-age=86400"
    return build.scan_overview(repo.scan_overview(session, scan.id))
