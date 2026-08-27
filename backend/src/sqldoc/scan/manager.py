"""ScanManager: runs scans on background threads, one at a time per connection."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from sqldoc.config.schema import AppConfig, ConnectionCfg, ScanOptions
from sqldoc.scan.orchestrator import run_scan
from sqldoc.scan.progress import PHASES, ScanProgress
from sqldoc.store import models as m
from sqldoc.store.db import Database
from sqldoc.store.models import utcnow

Runner = Callable[..., None]


class ScanAlreadyRunning(Exception):
    pass


@dataclass
class _Handle:
    connection: str
    thread: threading.Thread
    progress: ScanProgress


class ScanManager:
    def __init__(self, db: Database, cfg: AppConfig, runner: Runner = run_scan) -> None:
        self.db = db
        self.cfg = cfg
        self._runner = runner
        self._lock = threading.RLock()
        self._handles: dict[int, _Handle] = {}

    # -- control -------------------------------------------------------------------------
    def start(self, connection_name: str, options: ScanOptions | None = None) -> int:
        conn_cfg = self.cfg.connection(connection_name)
        options = options or self.cfg.scan
        with self._lock:
            running = self.running_for(conn_cfg.name)
            if running is not None:
                raise ScanAlreadyRunning(
                    f"scan {running} is already running for connection '{conn_cfg.name}'"
                )
            scan_id = self._create_row(conn_cfg, options)
            progress = ScanProgress(scan_id)
            thread = threading.Thread(
                target=self._run,
                args=(conn_cfg, scan_id, progress, options),
                name=f"sqldoc-scan-{scan_id}",
                daemon=True,
            )
            self._handles[scan_id] = _Handle(conn_cfg.name, thread, progress)
            thread.start()
            return scan_id

    def cancel(self, scan_id: int) -> bool:
        handle = self._handles.get(scan_id)
        if handle is None or not handle.thread.is_alive():
            return False
        handle.progress.cancel()
        return True

    def wait(self, scan_id: int, timeout: float | None = None) -> bool:
        handle = self._handles.get(scan_id)
        if handle is None:
            return True
        handle.thread.join(timeout)
        return not handle.thread.is_alive()

    def running_for(self, connection_name: str) -> int | None:
        with self._lock:
            handles = list(self._handles.items())
        for scan_id, handle in handles:
            if (
                handle.connection.casefold() == connection_name.casefold()
                and handle.thread.is_alive()
            ):
                return scan_id
        return None

    # -- read ----------------------------------------------------------------------------
    def progress(self, scan_id: int) -> dict[str, Any] | None:
        handle = self._handles.get(scan_id)
        if handle is not None and handle.thread.is_alive():
            return handle.progress.snapshot()
        with self.db.session() as s:
            scan = s.get(m.Scan, scan_id)
            if scan is None:
                return None
            warnings = (
                s.execute(select(m.ScanWarning).where(m.ScanWarning.scan_id == scan_id))
                .scalars()
                .all()
            )
            snap = handle.progress.snapshot() if handle is not None else {}
            terminal = scan.status != "running"
            phase = "finalize" if scan.status == "succeeded" else scan.phase
            phase_index = PHASES.index(phase) + 1 if phase in PHASES else snap.get("phase_index", 0)
            return {
                "scan_id": scan.id,
                "status": scan.status,
                "phase": phase,
                "phase_index": phase_index,
                "phase_count": len(PHASES),
                "current": 1 if terminal else snap.get("current", 0),
                "total": 1 if terminal else snap.get("total", 0),
                "message": snap.get("message", ""),
                "started_at": scan.started_at,
                "updated_at": scan.finished_at or scan.started_at,
                "finished_at": scan.finished_at,
                "error": scan.error,
                "warnings": [
                    {
                        "phase": w.phase,
                        "code": w.code,
                        "message": w.message,
                        "database": w.database_name,
                    }
                    for w in warnings
                ],
                "log": snap.get("log", []),
                "summary": json.loads(scan.summary_json) if scan.summary_json else None,
            }

    # -- internals -----------------------------------------------------------------------
    def _create_row(self, conn_cfg: ConnectionCfg, options: ScanOptions) -> int:
        with self.db.session() as s:
            scan = m.Scan(
                connection_name=conn_cfg.name,
                status="running",
                started_at=utcnow(),
                options_json=json.dumps(options.model_dump()),
                config_json=json.dumps(
                    conn_cfg.model_dump(mode="json")
                ),  # SecretStr -> "**********"
            )
            s.add(scan)
            s.commit()
            return scan.id

    def _run(
        self, conn_cfg: ConnectionCfg, scan_id: int, progress: ScanProgress, options: ScanOptions
    ) -> None:
        try:
            self._runner(self.db, self.cfg, conn_cfg, scan_id, progress, options)
        except Exception as exc:  # noqa: BLE001 - surfaced through the scan row
            self._finalize_if_running(scan_id, "failed", f"{exc.__class__.__name__}: {exc}")
            if progress.status == "running":
                progress.finish("failed", str(exc))
            return
        self._finalize_if_running(scan_id, "succeeded", None)
        if progress.status == "running":
            progress.finish("succeeded")

    def _finalize_if_running(self, scan_id: int, status: str, error: str | None) -> None:
        with self.db.session() as s:
            scan = s.get(m.Scan, scan_id)
            if scan is not None and scan.status == "running":
                scan.status = status
                scan.error = error
                scan.finished_at = utcnow()
                s.commit()
