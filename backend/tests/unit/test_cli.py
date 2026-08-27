"""Typer CLI over a temp config + SQLite."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sqldoc.cli import app
from sqldoc.scan import orchestrator
from sqldoc.store import models as m
from sqldoc.store.db import Database

runner = CliRunner()

CONFIG = """
version: 1
storage: { sqlite_path: data.sqlite }
connections:
  - name: local-aw
    host: localhost
    port: 1433
    auth: { mode: sql, username: sa, password: "pw" }
    databases:
      - { name: AdventureWorks2022, schemas: [Sales, HumanResources] }
  - name: dw
    host: sqlprod01
    auth: { mode: integrated }
    databases:
      - { name: DW, schemas: [dbo] }
"""


@pytest.fixture
def config_path(tmp_path) -> Path:
    p = tmp_path / "sqldoc.yaml"
    p.write_text(CONFIG)
    return p


def invoke(config_path, *args):
    return runner.invoke(app, ["--config", str(config_path), *args])


def test_connections_list(config_path):
    result = invoke(config_path, "connections", "list")
    assert result.exit_code == 0, result.output
    assert "local-aw" in result.output and "localhost:1433" in result.output
    assert "AdventureWorks2022" in result.output and "Sales" in result.output
    assert "dw" in result.output and "integrated" in result.output
    assert "pw" not in result.output


def test_scan_runs_all_connections_and_reports(config_path, monkeypatch):
    calls = []

    def fake_run_scan(db, cfg, conn_cfg, scan_id, progress, options, **kw):
        calls.append(conn_cfg.name)
        progress.start_phase("finalize", total=1)
        progress.advance()
        with db.session() as s:
            scan = s.get(m.Scan, scan_id)
            scan.status = "succeeded"
            scan.summary_json = json.dumps({"tables": 3})
            s.commit()
        progress.finish("succeeded")

    monkeypatch.setattr(orchestrator, "run_scan", fake_run_scan)
    result = invoke(config_path, "scan")
    assert result.exit_code == 0, result.output
    assert calls == ["local-aw", "dw"]
    assert "succeeded" in result.output
    assert (config_path.parent / "data.sqlite").exists()


def test_scan_failure_sets_exit_code(config_path, monkeypatch):
    def fake_run_scan(db, cfg, conn_cfg, scan_id, progress, options, **kw):
        raise RuntimeError("cannot connect")

    monkeypatch.setattr(orchestrator, "run_scan", fake_run_scan)
    result = invoke(config_path, "scan", "--connection", "dw")
    assert result.exit_code == 1
    assert "cannot connect" in result.output


def test_scans_list_and_prune(config_path, monkeypatch):
    def fake_run_scan(db, cfg, conn_cfg, scan_id, progress, options, **kw):
        with db.session() as s:
            scan = s.get(m.Scan, scan_id)
            scan.status = "succeeded"
            s.commit()

    monkeypatch.setattr(orchestrator, "run_scan", fake_run_scan)
    for _ in range(3):
        assert invoke(config_path, "scan", "--connection", "local-aw").exit_code == 0
    listing = invoke(config_path, "scans", "list")
    assert listing.exit_code == 0 and listing.output.count("succeeded") == 3

    pruned = invoke(config_path, "scans", "prune", "--keep", "1")
    assert pruned.exit_code == 0 and "2" in pruned.output
    db = Database.open(config_path.parent / "data.sqlite")
    with db.session() as s:
        assert s.query(m.Scan).count() == 1


def test_db_upgrade_creates_database(config_path):
    result = invoke(config_path, "db", "upgrade")
    assert result.exit_code == 0
    assert (config_path.parent / "data.sqlite").exists()


def test_missing_config_is_a_clean_error(tmp_path):
    result = runner.invoke(app, ["--config", str(tmp_path / "nope.yaml"), "connections", "list"])
    assert result.exit_code == 1
    assert "not found" in result.output
