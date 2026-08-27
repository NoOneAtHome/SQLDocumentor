"""Scan-scoped responses may only be cached once the scan is terminal."""

from datetime import UTC, datetime

from sqlalchemy import select

from sqldoc.store import models as m
from tests.unit import test_api_support as support

seeded = support.seeded
client = support.client


def set_status(seeded, status: str) -> None:
    with seeded.runtime.db.session() as s:
        scan = s.get(m.Scan, seeded.seed.scan_id)
        scan.status = status
        scan.finished_at = datetime.now(UTC).replace(tzinfo=None) if status != "running" else None
        s.commit()


def add_edge(seeded, source_key: str, target_key: str) -> None:
    """Add a column edge between the first columns of two objects."""
    with seeded.runtime.db.session() as s:
        sid = seeded.seed.scan_id
        cols = {}
        for key in (source_key, target_key):
            cols[key] = (
                s.execute(
                    select(m.Column)
                    .where(m.Column.scan_id == sid, m.Column.object_id == seeded.seed.ids[key])
                    .order_by(m.Column.ordinal)
                )
                .scalars()
                .first()
            )
        s.add(
            m.ColumnLineage(
                scan_id=sid,
                source_object_id=cols[source_key].object_id,
                source_column_id=cols[source_key].id,
                target_object_id=cols[target_key].object_id,
                target_column_id=cols[target_key].id,
                confidence="exact",
                transform="passthrough",
                statement_kind="view",
            )
        )
        s.commit()


def key(e: dict) -> tuple:
    return (e["source"], e["source_column"], e["target"], e["target_column"])


def test_lineage_is_not_cached_while_the_scan_is_running(client, seeded):
    sid, ids = seeded.seed.scan_id, seeded.seed.ids
    try:
        set_status(seeded, "running")
        params = {"focus": ids["view"], "direction": "both", "depth": 3}
        r = client.get(f"/api/scans/{sid}/lineage/columns", params=params)
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache"
        before = {key(e) for e in r.json()["edges"]}

        add_edge(seeded, "person", "view")
        r = client.get(f"/api/scans/{sid}/lineage/columns", params=params)
        after = {key(e) for e in r.json()["edges"]}
        assert after > before, "graph served from a stale in-process cache while running"

        d = client.get(f"/api/scans/{sid}/objects/{ids['view']}/definition")
        assert d.headers["cache-control"] == "no-cache"
    finally:
        set_status(seeded, "succeeded")

    r = client.get(f"/api/scans/{sid}/lineage/columns", params=params)
    assert r.headers["cache-control"] == "max-age=86400"
    assert {key(e) for e in r.json()["edges"]} == after
    d = client.get(f"/api/scans/{sid}/objects/{ids['view']}/definition")
    assert d.headers["cache-control"] == "max-age=86400"
