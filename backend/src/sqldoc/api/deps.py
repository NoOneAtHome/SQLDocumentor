"""FastAPI dependencies: runtime, per-request session, scan lookup, cache headers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from sqldoc.runtime import Runtime
from sqldoc.store import models as m
from sqldoc.store import repo


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]


def get_session(rt: RuntimeDep) -> Iterator[Session]:
    session = rt.db.session()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def get_scan(scan_id: int, session: SessionDep) -> m.Scan:
    scan = repo.get_scan(session, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail=f"scan {scan_id} not found")
    return scan


ScanDep = Annotated[m.Scan, Depends(get_scan)]


TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


def cache_snapshot(response: Response, scan: ScanDep) -> None:
    """Snapshot data is immutable once the scan is terminal; revalidate while it is written."""
    response.headers["Cache-Control"] = "max-age=86400" if scan.status in TERMINAL else "no-cache"


def cache_mutable(response: Response) -> None:
    """Snapshot data mixed with user annotations/tags: always revalidate."""
    response.headers["Cache-Control"] = "no-cache"


def csv_set(value: str | None) -> frozenset[str] | None:
    if value is None:
        return None
    items = frozenset(v.strip() for v in value.split(",") if v.strip())
    return items or None
