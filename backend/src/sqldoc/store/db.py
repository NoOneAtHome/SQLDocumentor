"""Engine/session factory for the SQLite store, with migrations applied on open."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from sqldoc.store import models as m

PRAGMAS = (
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
)


def make_engine(path: Path | str) -> Engine:
    url = f"sqlite:///{path}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _record) -> None:  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        for pragma in PRAGMAS:
            cur.execute(pragma)
        cur.close()

    return engine


def migrations_dir() -> Path:
    return Path(str(resources.files("sqldoc.store") / "migrations"))


def upgrade(engine: Engine) -> None:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(migrations_dir()))
    cfg.attributes["connection"] = None
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


class Database:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def open(cls, path: Path | str) -> Database:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = make_engine(path)
        upgrade(engine)
        return cls(engine)

    def session(self) -> Session:
        return self._sessions()

    def latest_scan_id(self, session: Session, connection: str) -> int | None:
        stmt = (
            select(m.Scan.id)
            .where(m.Scan.connection_name == connection, m.Scan.status == "succeeded")
            .order_by(m.Scan.finished_at.desc(), m.Scan.id.desc())
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()
