"""Everything a process needs: config, SQLite store, scan manager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqldoc.config import AppConfig, load_config
from sqldoc.scan import orchestrator
from sqldoc.scan.manager import ScanManager
from sqldoc.store.db import Database


@dataclass
class Runtime:
    cfg: AppConfig
    db: Database
    manager: ScanManager
    config_path: Path

    @classmethod
    def load(cls, config_path: Path | str, db_path: Path | str | None = None) -> Runtime:
        config_path = Path(config_path)
        cfg = load_config(config_path)
        sqlite_path = Path(db_path) if db_path else cfg.storage.sqlite_path
        db = Database.open(sqlite_path)
        manager = ScanManager(db, cfg, runner=orchestrator.run_scan)
        return cls(cfg=cfg, db=db, manager=manager, config_path=config_path)

    @property
    def sqlite_path(self) -> Path:
        return Path(str(self.db.engine.url.database))
