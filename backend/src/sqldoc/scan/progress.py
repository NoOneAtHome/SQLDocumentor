"""Thread-safe progress state shared between the scan thread and the API/CLI."""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

PHASES: tuple[str, ...] = (
    "connect",
    "enumerate",
    "cascade",
    "extract",
    "stats",
    "lineage",
    "finalize",
)


class ScanCancelled(Exception):
    """Raised at a checkpoint after ``ScanProgress.cancel()``."""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ScanProgress:
    def __init__(self, scan_id: int) -> None:
        self.scan_id = scan_id
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.status = "running"
        self.phase: str | None = None
        self.phase_index = 0
        self.current = 0
        self.total = 0
        self.message = ""
        self.started_at = _now()
        self.updated_at = self.started_at
        self.finished_at: datetime | None = None
        self.error: str | None = None
        self.warnings: list[dict[str, Any]] = []
        self.log: deque[dict[str, Any]] = deque(maxlen=200)

    # -- updates -------------------------------------------------------------------
    def start_phase(self, phase: str, total: int = 0, message: str = "") -> None:
        with self._lock:
            self.phase = phase
            self.phase_index = PHASES.index(phase) + 1 if phase in PHASES else 0
            self.current = 0
            self.total = total
            self.message = message
            self._touch(f"{phase}: {message}" if message else phase)

    def advance(self, current: int | None = None, message: str | None = None) -> None:
        with self._lock:
            self.current = self.current + 1 if current is None else current
            if message is not None:
                self.message = message
            self._touch(None)

    def set_total(self, total: int) -> None:
        with self._lock:
            self.total = total

    def warn(self, phase: str, code: str, message: str, database: str | None = None) -> None:
        with self._lock:
            self.warnings.append(
                {"phase": phase, "code": code, "message": message, "database": database}
            )
            self._touch(f"warning [{code}] {message}", level="warning")

    def finish(self, status: str, error: str | None = None) -> None:
        with self._lock:
            self.status = status
            self.error = error
            self.finished_at = _now()
            self._touch(f"finished: {status}" + (f" ({error})" if error else ""))

    def _touch(self, entry: str | None, level: str = "info") -> None:
        self.updated_at = _now()
        if entry:
            self.log.append({"ts": self.updated_at.isoformat(), "level": level, "message": entry})

    # -- cancellation --------------------------------------------------------------
    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise ScanCancelled(f"scan {self.scan_id} cancelled")

    # -- read ----------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "scan_id": self.scan_id,
                "status": self.status,
                "phase": self.phase,
                "phase_index": self.phase_index,
                "phase_count": len(PHASES),
                "current": self.current,
                "total": self.total,
                "message": self.message,
                "started_at": self.started_at,
                "updated_at": self.updated_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "warnings": [dict(w) for w in self.warnings],
                "log": [dict(entry) for entry in self.log],
            }
