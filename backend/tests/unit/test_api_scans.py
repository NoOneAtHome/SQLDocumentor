"""Scan lifecycle endpoints."""

import time

from tests.unit import test_api_support as support

seeded = support.seeded
client = support.client


def wait_for(client, scan_id, status, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/scans/{scan_id}").json()
        if body["status"] == status:
            return body
        time.sleep(0.02)
    raise AssertionError(f"scan {scan_id} never reached {status}")


def test_list_scans_for_connection(client, seeded):
    r = client.get("/api/connections/local/scans")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and body["limit"] == 20 and body["offset"] == 0
    latest, failed = body["items"]
    assert latest["id"] == seeded.seed.scan_id and latest["connection"] == "local"
    assert latest["status"] == "succeeded" and latest["duration_ms"] >= 9000
    assert latest["options"]["parse_lineage"] is True
    assert latest["counts"] == {
        "databases": 1,
        "schemas": 3,
        "tables": 3,
        "views": 1,
        "procedures": 1,
        "functions": 1,
        "triggers": 1,
        "synonyms": 0,
        "externals": 1,
        "cascaded": 3,
        "columns": 12,
        "edges_object": 14,
        "edges_column": 5,
        "lineage_issues": 2,
        "warnings": 1,
    }
    assert latest["server_version"] == "16.0.4000.1"
    assert failed["status"] == "failed" and "Login failed" in failed["error"]
    assert failed["counts"] is None
    assert (
        client.get("/api/connections/local/scans?limit=1").json()["items"][0]["id"] == latest["id"]
    )
    assert client.get("/api/connections/nope/scans").status_code == 404


def test_get_scan_status_for_finished_scan(client, seeded):
    r = client.get(f"/api/scans/{seeded.seed.scan_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "succeeded"
    assert body["progress"]["phase"] == "finalize" and body["progress"]["phase_count"] == 7
    assert body["warnings"] == [
        {
            "phase": "stats",
            "code": "stats_unavailable",
            "message": "dm_db_missing_index_group_stats: permission denied",
            "database": "AW",
        }
    ]
    assert body["counts"]["tables"] == 3
    assert "cache-control" not in {k.lower() for k in r.headers}
    assert client.get("/api/scans/999999").status_code == 404


def test_start_scan_conflict_progress_and_cancel(client, seeded):
    runner = seeded.runner
    runner.gate.clear()
    try:
        r = client.post("/api/connections/local/scans", json={"collect_stats": False})
        assert r.status_code == 202, r.text
        scan_id = r.json()["scan_id"]
        assert client.post("/api/connections/local/scans").status_code == 409
        conns = client.get("/api/connections").json()["items"]
        assert conns[0]["running_scan_id"] == scan_id
        body = client.get(f"/api/scans/{scan_id}").json()
        assert body["status"] == "running" and body["progress"]["phase"] == "connect"
        assert body["progress"]["message"] == "stub" and body["counts"] is None
        assert client.delete(f"/api/scans/{scan_id}").status_code == 409
        r = client.post(f"/api/scans/{scan_id}/cancel")
        assert r.status_code == 200 and r.json() == {"scan_id": scan_id, "cancelled": True}
        body = wait_for(client, scan_id, "cancelled")
        assert body["finished_at"] is not None
    finally:
        runner.gate.set()
    assert runner.calls[-1][1].collect_stats is False
    # cancel on a finished scan is a no-op
    assert client.post(f"/api/scans/{scan_id}/cancel").json()["cancelled"] is False
    assert client.post("/api/scans/999999/cancel").status_code == 404


def test_start_scan_completes_and_can_be_deleted(client, seeded):
    r = client.post("/api/connections/local/scans")
    assert r.status_code == 202
    scan_id = r.json()["scan_id"]
    body = wait_for(client, scan_id, "succeeded")
    assert body["counts"]["tables"] == 0
    assert client.delete(f"/api/scans/{scan_id}").status_code == 204
    assert client.get(f"/api/scans/{scan_id}").status_code == 404
    assert client.delete(f"/api/scans/{scan_id}").status_code == 404
    assert client.post("/api/connections/nope/scans").status_code == 404


def test_scan_summary(client, seeded):
    sid = seeded.seed.scan_id
    r = client.get(f"/api/scans/{sid}/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["databases"][0]["name"] == "AW" and body["databases"][0]["is_configured"]
    schemas = {s["name"]: s for s in body["databases"][0]["schemas"]}
    assert set(schemas) == {"Sales", "Person", "dbo"}
    assert schemas["Sales"]["is_selected"] and schemas["Sales"]["counts_by_kind"]["table"] == 1
    assert body["counts"]["tables"] == 3
    assert body["lineage_coverage"] == 0.75
    assert body["warnings_summary"] == {
        "lineage_issues": 2,
        "unused_indexes": 1,
        "missing_index_suggestions": 2,
        "external_refs": 1,
    }
    assert body["warnings"][0]["code"] == "stats_unavailable"
    assert r.headers["cache-control"] == "max-age=86400"
    assert client.get("/api/scans/999999/summary").status_code == 404
