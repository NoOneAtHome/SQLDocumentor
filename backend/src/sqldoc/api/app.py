"""Application factory: API routers under ``/api`` plus the built SPA as a low-priority mount."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqldoc import __version__
from sqldoc.api import schemas as S
from sqldoc.api.deps import RuntimeDep
from sqldoc.api.routers import annotations, connections, lineage, scans, snapshot, stats
from sqldoc.runtime import Runtime
from sqldoc.settings import Settings

# backend/src/sqldoc/api/app.py -> repo root -> frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parents[4] / "frontend" / "dist"
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app(runtime: Runtime | None = None) -> FastAPI:
    if runtime is None:
        settings = Settings()
        runtime = Runtime.load(settings.config, settings.db)

    app = FastAPI(title="SQL Documentor", version=__version__)
    app.state.runtime = runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api")
    api.include_router(connections.router)
    api.include_router(scans.router)
    api.include_router(snapshot.router)
    api.include_router(lineage.router)
    api.include_router(stats.router)
    api.include_router(annotations.router)

    @api.get("/health", response_model=S.Health, tags=["app"])
    def health(rt: RuntimeDep) -> S.Health:
        return S.Health(ok=True, version=__version__, db_path=str(rt.sqlite_path))

    @api.get("/config", response_model=S.ConfigOut, tags=["app"])
    def config(rt: RuntimeDep) -> S.ConfigOut:
        return S.ConfigOut(
            config_path=str(rt.config_path),
            sqlite_path=str(rt.sqlite_path),
            config=rt.cfg.model_dump(mode="json"),  # SecretStr -> "**********"
        )

    app.include_router(api)
    mount_frontend(app)
    return app


def mount_frontend(app: FastAPI, directory: Path = FRONTEND_DIST) -> None:
    """Serve ``frontend/dist`` with SPA fallback; API routes always take priority."""
    frontend = getattr(app, "frontend", None)
    if callable(frontend):  # FastAPI >= 0.141
        frontend("/", directory=str(directory), fallback="index.html", check_dir=False)
    elif directory.is_dir():  # pragma: no cover - older FastAPI
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(directory), html=True), name="frontend")
