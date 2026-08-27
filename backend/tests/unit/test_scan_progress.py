"""ScanProgress: phases, counters, warnings, cancellation."""

import pytest

from sqldoc.scan.progress import PHASES, ScanCancelled, ScanProgress


def test_phases_are_ordered():
    assert PHASES == ("connect", "enumerate", "cascade", "extract", "stats", "lineage", "finalize")


def test_snapshot_tracks_phase_and_counters():
    p = ScanProgress(scan_id=7)
    p.start_phase("enumerate", total=3, message="AdventureWorks2022")
    p.advance()
    p.advance(message="second")
    snap = p.snapshot()
    assert snap["scan_id"] == 7 and snap["status"] == "running"
    assert snap["phase"] == "enumerate" and snap["phase_index"] == 2 and snap["phase_count"] == 7
    assert snap["current"] == 2 and snap["total"] == 3 and snap["message"] == "second"
    assert snap["updated_at"] is not None


def test_warnings_and_finish():
    p = ScanProgress(scan_id=1)
    p.warn(phase="stats", code="permission_missing", message="no VIEW SERVER STATE", database="AW")
    p.finish("succeeded")
    snap = p.snapshot()
    assert snap["status"] == "succeeded" and snap["finished_at"] is not None
    assert snap["warnings"] == [
        {
            "phase": "stats",
            "code": "permission_missing",
            "message": "no VIEW SERVER STATE",
            "database": "AW",
        }
    ]


def test_snapshot_is_a_copy():
    p = ScanProgress(scan_id=1)
    snap = p.snapshot()
    snap["warnings"].append("x")
    assert p.snapshot()["warnings"] == []


def test_cancel_raises_at_checkpoints():
    p = ScanProgress(scan_id=1)
    p.check_cancelled()
    p.cancel()
    with pytest.raises(ScanCancelled):
        p.check_cancelled()
