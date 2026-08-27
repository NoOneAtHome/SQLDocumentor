"""`sqldoc` command line."""

from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from sqlalchemy import delete, select

from sqldoc.config import ConfigError
from sqldoc.config.schema import ScanOptions
from sqldoc.runtime import Runtime
from sqldoc.settings import Settings
from sqldoc.store import models as m

app = typer.Typer(
    no_args_is_help=True, help="SQL Documentor: document SQL Server schemas and lineage."
)
connections_app = typer.Typer(no_args_is_help=True, help="Inspect configured connections.")
scans_app = typer.Typer(no_args_is_help=True, help="List or prune stored scans.")
db_app = typer.Typer(no_args_is_help=True, help="Manage the local SQLite store.")
app.add_typer(connections_app, name="connections")
app.add_typer(scans_app, name="scans")
app.add_typer(db_app, name="db")

console = Console()
err_console = Console(stderr=True)


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", envvar="SQLDOC_CONFIG", help="Path to sqldoc.yaml"),
    ] = None,
    db: Annotated[
        Path | None, typer.Option("--db", envvar="SQLDOC_DB", help="SQLite path override")
    ] = None,
) -> None:
    settings = Settings()
    ctx.obj = {"config": config or settings.config, "db": db or settings.db}


def _runtime(ctx: typer.Context) -> Runtime:
    try:
        return Runtime.load(ctx.obj["config"], ctx.obj["db"])
    except ConfigError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc


# -- connections -----------------------------------------------------------------------


@connections_app.command("list")
def connections_list(ctx: typer.Context) -> None:
    rt = _runtime(ctx)
    table = Table("name", "server", "auth", "driver", "databases (schemas)")
    for c in rt.cfg.connections:
        dbs = "\n".join(f"{d.name} ({', '.join(d.schemas)})" for d in c.databases)
        auth = c.auth.mode if c.auth.mode == "integrated" else f"sql ({c.auth.username})"
        table.add_row(c.name, f"{c.host}:{c.port}", auth, c.driver, dbs)
    console.print(table)


@connections_app.command("test")
def connections_test(ctx: typer.Context, name: str) -> None:
    from sqldoc.mssql import driver as drv
    from sqldoc.mssql.catalog import CatalogExtractor
    from sqldoc.mssql.client import connect

    rt = _runtime(ctx)
    try:
        conn_cfg = rt.cfg.connection(name)
    except ConfigError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"driver diagnostics: {json.dumps(drv.diagnostics())}")
    try:
        client = connect(conn_cfg, conn_cfg.databases[0].name)
    except Exception as exc:  # noqa: BLE001 - report any driver error
        console.print(f"[red]connection failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    try:
        ex = CatalogExtractor(client)
        info = ex.server_info()
        console.print(
            f"[green]connected[/green] via {client.driver_name} to {info.get('server_name')} "
            f"({info.get('edition')} {info.get('product_version')})"
        )
        try:
            console.print(f"auth scheme: {ex.auth_scheme()}")
        except Exception as exc:  # noqa: BLE001
            console.print(f"auth scheme: unavailable ({exc})")
        for db_cfg in conn_cfg.databases:
            try:
                client.use_database(db_cfg.name)
                perms = ex.permissions()
                flags = ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in perms.items())
                console.print(f"  {db_cfg.name}: reachable; {flags}")
            except Exception as exc:  # noqa: BLE001
                console.print(f"  {db_cfg.name}: [red]unreachable[/red] ({exc})")
    finally:
        client.close()


# -- scan ------------------------------------------------------------------------------


@app.command()
def scan(
    ctx: typer.Context,
    connection: Annotated[
        list[str] | None, typer.Option("--connection", "-n", help="Connection name (repeatable)")
    ] = None,
    stats: Annotated[bool, typer.Option("--stats/--no-stats")] = True,
    lineage: Annotated[bool, typer.Option("--lineage/--no-lineage")] = True,
) -> None:
    """Scan one or more connections into the local SQLite store."""
    rt = _runtime(ctx)
    names = connection or [c.name for c in rt.cfg.connections]
    options = rt.cfg.scan.model_copy(update={"collect_stats": stats, "parse_lineage": lineage})
    failed = False
    for name in names:
        failed |= not _run_one(rt, name, options)
    if failed:
        raise typer.Exit(1)


def _run_one(rt: Runtime, name: str, options: ScanOptions) -> bool:
    try:
        scan_id = rt.manager.start(name, options)
    except Exception as exc:  # noqa: BLE001 - config / already-running errors
        console.print(f"[red]{name}:[/red] {exc}")
        return False
    with Progress(
        TextColumn("[bold]{task.fields[conn]}[/bold] {task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("starting", total=1, conn=name)
        while not rt.manager.wait(scan_id, timeout=0.2):
            snap = rt.manager.progress(scan_id) or {}
            progress.update(
                task,
                description=f"{snap.get('phase') or ''} {snap.get('message') or ''}".strip(),
                total=max(snap.get("total") or 1, 1),
                completed=snap.get("current") or 0,
            )
    snap = rt.manager.progress(scan_id) or {}
    status = snap.get("status")
    if status == "succeeded":
        summary = snap.get("summary") or {}
        console.print(
            f"[green]{name}: scan {scan_id} succeeded[/green] - "
            + ", ".join(
                f"{k}={v}"
                for k, v in summary.items()
                if k
                in (
                    "tables",
                    "views",
                    "procedures",
                    "functions",
                    "triggers",
                    "columns",
                    "edges_object",
                    "edges_column",
                    "cascaded",
                    "externals",
                    "warnings",
                )
            )
        )
        for w in snap.get("warnings") or []:
            console.print(f"  [yellow]warning[/yellow] [{w['code']}] {w['message']}")
        return True
    console.print(f"[red]{name}: scan {scan_id} {status}[/red] {snap.get('error') or ''}")
    return False


# -- scans -----------------------------------------------------------------------------


@scans_app.command("list")
def scans_list(
    ctx: typer.Context,
    connection: Annotated[str | None, typer.Option("--connection", "-n")] = None,
) -> None:
    rt = _runtime(ctx)
    table = Table("id", "connection", "status", "started (UTC)", "finished (UTC)", "summary")
    with rt.db.session() as s:
        stmt = select(m.Scan).order_by(m.Scan.id.desc())
        if connection:
            stmt = stmt.where(m.Scan.connection_name == connection)
        for scan_row in s.execute(stmt).scalars():
            summary = json.loads(scan_row.summary_json) if scan_row.summary_json else {}
            brief = ", ".join(
                f"{k}={summary[k]}" for k in ("tables", "views", "procedures") if k in summary
            )
            table.add_row(
                str(scan_row.id),
                scan_row.connection_name,
                scan_row.status,
                _fmt(scan_row.started_at),
                _fmt(scan_row.finished_at),
                brief,
            )
    console.print(table)


@scans_app.command("prune")
def scans_prune(
    ctx: typer.Context,
    keep: Annotated[int, typer.Option("--keep", help="Scans to keep per connection")] = 5,
) -> None:
    rt = _runtime(ctx)
    deleted = 0
    with rt.db.session() as s:
        for conn in {row[0] for row in s.execute(select(m.Scan.connection_name)).all()}:
            ids = [
                row[0]
                for row in s.execute(
                    select(m.Scan.id)
                    .where(m.Scan.connection_name == conn)
                    .order_by(m.Scan.id.desc())
                ).all()
            ]
            for old in ids[keep:]:
                s.execute(delete(m.Scan).where(m.Scan.id == old))
                deleted += 1
        s.commit()
    console.print(f"Deleted {deleted} scan(s), keeping the latest {keep} per connection.")


# -- serve / db ------------------------------------------------------------------------


@app.command()
def serve(
    ctx: typer.Context,
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int | None, typer.Option("--port")] = None,
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = False,
) -> None:
    """Serve the API and the built web UI."""
    import uvicorn

    from sqldoc.api.app import create_app

    settings = Settings()
    host = host or settings.host
    port = port or settings.port
    rt = _runtime(ctx)
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    console.print(f"SQL Documentor at {url} (config {rt.config_path}, store {rt.sqlite_path})")
    uvicorn.run(create_app(rt), host=host, port=port, log_level="info")


@db_app.command("upgrade")
def db_upgrade(ctx: typer.Context) -> None:
    """Create or migrate the SQLite store."""
    rt = _runtime(ctx)
    console.print(f"store ready: {rt.sqlite_path}")


def _fmt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


if __name__ == "__main__":  # pragma: no cover
    app()
