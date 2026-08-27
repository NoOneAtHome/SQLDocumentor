"""run_scan(): connect -> enumerate -> cascade -> extract -> stats -> lineage -> finalize.

Each phase commits before the next so a crash leaves a diagnosable partial scan.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable

from sqlalchemy import update
from sqlalchemy.orm import Session

from sqldoc.config.schema import AppConfig, ConnectionCfg, ScanOptions
from sqldoc.lineage.runner import run_lineage
from sqldoc.mssql.catalog import CatalogExtractor, RawDatabase
from sqldoc.mssql.client import MssqlClient, connect
from sqldoc.mssql.stats import StatsExtractor
from sqldoc.scan.progress import ScanCancelled, ScanProgress
from sqldoc.scope.adapt import (
    dependencies_from_raw,
    foreign_keys_from_raw,
    synonyms_from_raw,
    triggers_from_raw,
    universe_from_raw,
)
from sqldoc.scope.cascade import compute_closure
from sqldoc.store import models as m
from sqldoc.store import repo
from sqldoc.store.db import Database
from sqldoc.store.models import utcnow
from sqldoc.store.writer import SnapshotWriter

Connector = Callable[[ConnectionCfg, str], MssqlClient]
LineageRunner = Callable[[Session, SnapshotWriter, dict[str, RawDatabase], ScanProgress], None]


class _Ctx:
    def __init__(self, session: Session, scan: m.Scan, progress: ScanProgress) -> None:
        self.session, self.scan, self.progress = session, scan, progress

    def phase(self, name: str, total: int = 0, message: str = "") -> None:
        self.progress.check_cancelled()
        self.progress.start_phase(name, total=total, message=message)
        self.scan.phase = name
        self.session.commit()

    def warn(
        self,
        phase: str,
        code: str,
        message: str,
        database: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.progress.warn(phase, code, message, database)
        self.session.add(
            m.ScanWarning(
                scan_id=self.scan.id,
                phase=phase,
                database_name=database,
                code=code,
                message=message,
                detail=detail,
            )
        )


def run_scan(
    db: Database,
    cfg: AppConfig,
    conn_cfg: ConnectionCfg,
    scan_id: int,
    progress: ScanProgress,
    options: ScanOptions | None = None,
    *,
    connector: Connector = connect,
    lineage_runner: LineageRunner | None = None,
) -> None:
    options = options or cfg.scan
    client: MssqlClient | None = None
    try:
        with db.session() as session:
            scan = session.get(m.Scan, scan_id)
            if scan is None:
                raise RuntimeError(f"scan {scan_id} does not exist")
            ctx = _Ctx(session, scan, progress)
            writer = SnapshotWriter(session, scan_id, conn_cfg.name)

            # -- connect ---------------------------------------------------------------
            ctx.phase("connect", total=1, message=f"{conn_cfg.host}:{conn_cfg.port}")
            client = connector(conn_cfg, conn_cfg.databases[0].name)
            ex = CatalogExtractor(client)
            info = ex.server_info()
            scan.server_name = info.get("server_name")
            scan.server_version = info.get("product_version")
            scan.server_edition = info.get("edition")
            scan.driver = client.driver_name
            try:
                scan.auth_scheme = ex.auth_scheme()
            except Exception as exc:  # noqa: BLE001 - probe is optional
                ctx.warn("connect", "probe_failed", f"auth_scheme probe failed: {exc}")
            try:
                scan.server_start_time = ex.server_start_time()
            except Exception as exc:  # noqa: BLE001
                ctx.warn("connect", "probe_failed", f"server start time unavailable: {exc}")
            progress.advance()
            session.commit()

            # -- enumerate -------------------------------------------------------------
            ctx.phase("enumerate", total=len(conn_cfg.databases))
            raws: dict[str, RawDatabase] = {}
            perms: dict[str, dict[str, bool]] = {}
            for db_cfg in conn_cfg.databases:
                progress.check_cancelled()
                client.use_database(db_cfg.name)
                raw = RawDatabase(name=db_cfg.name, info=ex.database_info())
                raw.objects = ex.objects()
                raw.triggers = ex.triggers()
                raw.synonyms = ex.synonyms()
                raw.dependencies = ex.dependencies()
                raw.foreign_keys = ex.foreign_keys()
                raws[db_cfg.name] = raw
                perms[db_cfg.name] = ex.permissions()
                if perms[db_cfg.name].get("view_definition") is False:
                    ctx.warn(
                        "enumerate",
                        "no_view_definition",
                        "login lacks VIEW DEFINITION: definitions and lineage unavailable",
                        db_cfg.name,
                    )
                progress.advance(message=db_cfg.name)
            session.commit()

            # -- cascade ---------------------------------------------------------------
            ctx.phase("cascade", total=1)
            universe = universe_from_raw({name: raw.objects for name, raw in raws.items()})
            deps = [
                d
                for name, raw in raws.items()
                for d in dependencies_from_raw(name, raw.dependencies)
            ]
            fks = [
                f
                for name, raw in raws.items()
                for f in foreign_keys_from_raw(name, raw.foreign_keys)
            ]
            triggers = [
                t for name, raw in raws.items() for t in triggers_from_raw(name, raw.triggers)
            ]
            synonyms = [
                s for name, raw in raws.items() for s in synonyms_from_raw(name, raw.synonyms)
            ]
            closure = compute_closure(
                universe,
                deps,
                fks,
                triggers,
                synonyms,
                conn_cfg,
                options,
                server_name=scan.server_name,
            )
            progress.advance(message=f"{len(closure.scope)} objects in scope")
            session.commit()

            # -- extract ---------------------------------------------------------------
            ctx.phase("extract", total=len(conn_cfg.databases))
            for db_cfg in conn_cfg.databases:
                progress.check_cancelled()
                raw = raws[db_cfg.name]
                client.use_database(db_cfg.name)
                ex.details(raw)
                writer.write_database(raw, db_cfg, perms[db_cfg.name])
                writer.write_objects(raw, closure)
                writer.write_details(raw)
                progress.advance(message=db_cfg.name)
                session.commit()
            writer.write_externals(closure)
            writer.write_dependencies(closure)
            session.commit()

            # -- stats -----------------------------------------------------------------
            if options.collect_stats:
                ctx.phase("stats", total=len(conn_cfg.databases))
                for db_cfg in conn_cfg.databases:
                    progress.check_cancelled()
                    client.use_database(db_cfg.name)
                    stats = StatsExtractor(client, perms[db_cfg.name]).collect()
                    writer.write_stats(db_cfg.name, stats)
                    for w in stats.warnings:
                        ctx.warn("stats", w.code, w.message, db_cfg.name)
                    progress.advance(message=db_cfg.name)
                    session.commit()
            else:
                ctx.phase("stats", total=0, message="skipped (collect_stats: false)")

            # -- lineage ---------------------------------------------------------------
            if options.parse_lineage:
                ctx.phase("lineage", total=0)
                (lineage_runner or run_lineage)(session, writer, raws, progress)
            else:
                ctx.phase("lineage", total=0, message="skipped")
            session.execute(
                update(m.DbObject)
                .where(m.DbObject.scan_id == scan_id, m.DbObject.lineage_status == "pending")
                .values(lineage_status="skipped")
            )
            session.commit()

            # -- finalize --------------------------------------------------------------
            ctx.phase("finalize", total=1)
            scan.summary_json = json.dumps(repo.scan_counts(session, scan_id))
            scan.status = "succeeded"
            scan.finished_at = utcnow()
            progress.advance()
            session.commit()
            progress.finish("succeeded")
    except ScanCancelled:
        _mark(db, scan_id, "cancelled", None)
        progress.finish("cancelled")
        raise
    except Exception as exc:
        error = f"{exc.__class__.__name__}: {exc}"
        _mark(db, scan_id, "failed", error + "\n" + traceback.format_exc()[-4000:])
        progress.finish("failed", error)
        raise
    finally:
        if client is not None:
            client.close()


def _mark(db: Database, scan_id: int, status: str, error: str | None) -> None:
    with db.session() as session:
        scan = session.get(m.Scan, scan_id)
        if scan is not None:
            scan.status = status
            scan.error = error
            scan.finished_at = utcnow()
            session.commit()
