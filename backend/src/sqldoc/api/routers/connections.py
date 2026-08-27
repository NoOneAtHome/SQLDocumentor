"""Connections: read-only config listing and a live connection test."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, HTTPException

from sqldoc.api import build
from sqldoc.api import schemas as S
from sqldoc.api.deps import RuntimeDep, SessionDep
from sqldoc.config import ConfigError
from sqldoc.config.schema import ConnectionCfg
from sqldoc.mssql.catalog import CatalogExtractor
from sqldoc.mssql.client import connect
from sqldoc.runtime import Runtime
from sqldoc.store import repo

router = APIRouter(prefix="/connections", tags=["connections"])


def connection_or_404(rt: Runtime, name: str) -> ConnectionCfg:
    try:
        return rt.cfg.connection(name)
    except ConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _error(exc: BaseException) -> str:
    return f"{exc.__class__.__name__}: {exc}"


def probe_connection(cfg: ConnectionCfg) -> S.ConnectionTestResult:
    """Connect, read server info + auth scheme, probe permissions per database.

    Never raises: failures are reported as ``ok: false`` / per-database ``reachable``.
    """
    try:
        client = connect(cfg, cfg.databases[0].name)
    except Exception as exc:  # noqa: BLE001 - surfaced in the payload
        return S.ConnectionTestResult(
            ok=False,
            error=_error(exc),
            databases=[
                S.ConnectionTestDatabase(name=d.name, reachable=False, error=_error(exc))
                for d in cfg.databases
            ],
        )
    try:
        ex = CatalogExtractor(client)
        info = ex.server_info()
        try:
            auth_scheme = ex.auth_scheme()
        except Exception:  # noqa: BLE001 - optional probe
            auth_scheme = None
        server_state: bool | None = None
        databases: list[S.ConnectionTestDatabase] = []
        for d in cfg.databases:
            try:
                client.use_database(d.name)
                perms = ex.permissions()
            except Exception as exc:  # noqa: BLE001
                databases.append(
                    S.ConnectionTestDatabase(name=d.name, reachable=False, error=_error(exc))
                )
                continue
            if server_state is None:
                server_state = perms.get("view_server_state")
            databases.append(
                S.ConnectionTestDatabase(
                    name=d.name,
                    reachable=True,
                    can_view_definition=perms.get("view_definition"),
                    can_view_database_state=perms.get("view_database_state"),
                )
            )
        return S.ConnectionTestResult(
            ok=True,
            server_name=info.get("server_name"),
            version=info.get("product_version"),
            edition=info.get("edition"),
            auth_scheme=auth_scheme,
            driver=getattr(client, "driver_name", None),
            can_view_server_state=server_state,
            databases=databases,
        )
    except Exception as exc:  # noqa: BLE001
        return S.ConnectionTestResult(ok=False, error=_error(exc))
    finally:
        with contextlib.suppress(Exception):  # best effort
            client.close()


@router.get("", response_model=S.ListEnvelope[S.ConnectionInfo])
def list_connections(rt: RuntimeDep, session: SessionDep) -> S.ListEnvelope[S.ConnectionInfo]:
    items: list[S.ConnectionInfo] = []
    for c in rt.cfg.connections:
        latest = repo.latest_scan(session, c.name)
        items.append(
            S.ConnectionInfo(
                name=c.name,
                host=c.host,
                port=c.port,
                auth_mode=c.auth.mode,
                username=c.auth.username,
                driver=c.driver,
                databases=[
                    S.ConnectionDatabase(name=d.name, schemas=list(d.schemas)) for d in c.databases
                ],
                latest_scan=build.scan_summary(latest) if latest else None,
                running_scan_id=rt.manager.running_for(c.name),
            )
        )
    return S.ListEnvelope(items=items, total=len(items), limit=len(items), offset=0)


@router.post("/{name}/test", response_model=S.ConnectionTestResult)
def test_connection(name: str, rt: RuntimeDep) -> S.ConnectionTestResult:
    return probe_connection(connection_or_404(rt, name))
