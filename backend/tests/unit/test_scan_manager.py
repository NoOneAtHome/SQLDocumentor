"""ScanManager: background thread, single flight per connection, failure marking."""

import threading

import pytest

from sqldoc.config.errors import ConfigError
from sqldoc.config.schema import AppConfig, AuthCfg, ConnectionCfg, DatabaseCfg
from sqldoc.scan.manager import ScanAlreadyRunning, ScanManager
from sqldoc.store import models as m
from sqldoc.store.db import Database


def app_cfg() -> AppConfig:
    return AppConfig(
        connections=[
            ConnectionCfg(
                name="c1",
                host="h",
                auth=AuthCfg(mode="integrated"),
                databases=[DatabaseCfg(name="AW", schemas=["Sales"])],
            ),
            ConnectionCfg(
                name="c2",
                host="h",
                auth=AuthCfg(mode="integrated"),
                databases=[DatabaseCfg(name="AW", schemas=["Sales"])],
            ),
        ]
    )


@pytest.fixture
def db(tmp_path):
    return Database.open(tmp_path / "m.sqlite")


def test_start_runs_in_background_and_records_success(db):
    seen = {}

    def runner(db_, cfg, conn_cfg, scan_id, progress, options):
        seen["conn"] = conn_cfg.name
        progress.start_phase("connect", total=1)
        progress.finish("succeeded")
        with db_.session() as s:
            scan = s.get(m.Scan, scan_id)
            scan.status = "succeeded"
            s.commit()

    mgr = ScanManager(db, app_cfg(), runner=runner)
    scan_id = mgr.start("c1")
    assert mgr.wait(scan_id, timeout=5)
    assert seen["conn"] == "c1"
    assert mgr.running_for("c1") is None
    snap = mgr.progress(scan_id)
    assert snap["status"] == "succeeded" and snap["scan_id"] == scan_id
    # a finished scan reports the final phase as complete, even after a process restart
    fresh = ScanManager(db, app_cfg(), runner=runner)
    snap = fresh.progress(scan_id)
    assert snap["status"] == "succeeded"
    assert snap["phase"] == "finalize" and snap["phase_index"] == 7
    assert snap["current"] == snap["total"] == 1


def test_single_flight_per_connection_but_parallel_across_connections(db):
    gate = threading.Event()

    def runner(db_, cfg, conn_cfg, scan_id, progress, options):
        gate.wait(5)

    mgr = ScanManager(db, app_cfg(), runner=runner)
    a = mgr.start("c1")
    with pytest.raises(ScanAlreadyRunning):
        mgr.start("c1")
    b = mgr.start("c2")
    assert mgr.running_for("c1") == a and mgr.running_for("c2") == b
    assert mgr.progress(a)["status"] == "running"
    gate.set()
    assert mgr.wait(a, 5) and mgr.wait(b, 5)
    assert mgr.running_for("c1") is None


def test_runner_exception_marks_scan_failed(db):
    def runner(*args, **kwargs):
        raise RuntimeError("boom")

    mgr = ScanManager(db, app_cfg(), runner=runner)
    scan_id = mgr.start("c1")
    assert mgr.wait(scan_id, 5)
    with db.session() as s:
        scan = s.get(m.Scan, scan_id)
    assert scan.status == "failed" and "boom" in scan.error
    assert mgr.progress(scan_id)["status"] == "failed"


def test_unknown_connection_is_an_error(db):
    mgr = ScanManager(db, app_cfg(), runner=lambda *a, **k: None)
    with pytest.raises(ConfigError):
        mgr.start("nope")


def test_scan_row_has_sanitized_config(db):
    cfg = app_cfg()
    cfg.connections[0].auth = AuthCfg(mode="sql", username="sa", password="hunter2")
    mgr = ScanManager(db, cfg, runner=lambda *a, **k: None)
    scan_id = mgr.start("c1")
    mgr.wait(scan_id, 5)
    with db.session() as s:
        scan = s.get(m.Scan, scan_id)
    assert "hunter2" not in (scan.config_json or "")
    assert '"username": "sa"' in scan.config_json


def test_running_for_takes_the_manager_lock(db):
    """Readers must serialize with start(); otherwise _handles can change under iteration."""
    mgr = ScanManager(db, app_cfg(), runner=lambda *a, **k: None)
    results: list[int | None] = []
    with mgr._lock:  # noqa: SLF001 - exercising the locking contract
        t = threading.Thread(target=lambda: results.append(mgr.running_for("c1")))
        t.start()
        t.join(0.3)
        assert t.is_alive(), "running_for() returned without waiting for the lock"
    t.join(2)
    assert not t.is_alive() and results == [None]
