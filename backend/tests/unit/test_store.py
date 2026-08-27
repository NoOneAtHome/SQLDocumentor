"""SQLite snapshot store: schema creation, pragmas, cascade delete, identity keys."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from sqldoc.store import models as m
from sqldoc.store.db import Database


@pytest.fixture
def db(tmp_path) -> Database:
    return Database.open(tmp_path / "test.sqlite")


def new_scan(session, connection="local") -> m.Scan:
    scan = m.Scan(connection_name=connection, status="running", started_at=datetime.now(UTC))
    session.add(scan)
    session.flush()
    return scan


def test_open_creates_schema_and_sets_pragmas(db):
    with db.session() as s:
        assert s.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert s.execute(text("PRAGMA foreign_keys")).scalar() == 1
        tables = {
            r[0] for r in s.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    expected = {
        "scans",
        "databases",
        "objects",
        "columns",
        "parameters",
        "indexes",
        "index_columns",
        "foreign_keys",
        "foreign_key_columns",
        "check_constraints",
        "object_dependencies",
        "column_lineage",
        "table_stats",
        "index_usage",
        "proc_stats",
        "missing_indexes",
        "lineage_issues",
        "scan_warnings",
        "annotations",
        "tags",
        "tag_assignments",
        "meta",
    }
    assert expected <= tables


def test_open_is_idempotent(tmp_path):
    Database.open(tmp_path / "x.sqlite")
    Database.open(tmp_path / "x.sqlite")  # second open must not fail on existing tables


def test_deleting_scan_cascades_to_snapshot_rows(db):
    with db.session() as s:
        scan = new_scan(s)
        database = m.SnapshotDatabase(scan_id=scan.id, name="AW", is_configured=True)
        s.add(database)
        s.flush()
        obj = m.DbObject(
            scan_id=scan.id,
            database_id=database.id,
            object_key="local|AW|Sales|Customer",
            schema_name="Sales",
            name="Customer",
            kind="table",
            scope="in_scope",
        )
        s.add(obj)
        s.flush()
        s.add(
            m.Column(
                scan_id=scan.id,
                object_id=obj.id,
                column_key=obj.object_key + "|CustomerID",
                ordinal=1,
                name="CustomerID",
                type_name="int",
                type_display="int",
            )
        )
        s.commit()
        scan_id = scan.id
    with db.session() as s:
        s.delete(s.get(m.Scan, scan_id))
        s.commit()
    with db.session() as s:
        assert s.execute(select(m.DbObject)).all() == []
        assert s.execute(select(m.Column)).all() == []
        assert s.execute(select(m.SnapshotDatabase)).all() == []


def test_object_key_unique_within_scan_but_not_across_scans(db):
    with db.session() as s:
        a, b = new_scan(s), new_scan(s)
        for scan in (a, b):
            s.add(
                m.DbObject(
                    scan_id=scan.id,
                    object_key="k",
                    schema_name="dbo",
                    name="t",
                    kind="table",
                    scope="in_scope",
                )
            )
        s.commit()
        s.add(
            m.DbObject(
                scan_id=a.id,
                object_key="k",
                schema_name="dbo",
                name="t",
                kind="table",
                scope="in_scope",
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_latest_succeeded_scan_per_connection(db):
    with db.session() as s:
        s1 = new_scan(s, "c1")
        s1.status, s1.finished_at = "succeeded", datetime(2026, 1, 1, tzinfo=UTC)
        s2 = new_scan(s, "c1")
        s2.status, s2.finished_at = "succeeded", datetime(2026, 2, 1, tzinfo=UTC)
        s3 = new_scan(s, "c1")
        s3.status, s3.finished_at = "failed", datetime(2026, 3, 1, tzinfo=UTC)
        other = new_scan(s, "c2")
        other.status, other.finished_at = "succeeded", datetime(2026, 4, 1, tzinfo=UTC)
        s.commit()
        assert db.latest_scan_id(s, "c1") == s2.id
        assert db.latest_scan_id(s, "c2") == other.id
        assert db.latest_scan_id(s, "nope") is None


def test_annotation_target_key_is_case_insensitive_unique(db):
    with db.session() as s:
        s.add(m.Annotation(target_kind="object", target_key="local|AW|Sales|Customer", notes="n"))
        s.commit()
        found = s.execute(
            select(m.Annotation).where(m.Annotation.target_key == "LOCAL|aw|sales|CUSTOMER")
        ).scalar_one_or_none()
        assert found is not None and found.notes == "n"
        s.add(m.Annotation(target_kind="object", target_key="LOCAL|AW|SALES|CUSTOMER", notes="dup"))
        with pytest.raises(IntegrityError):
            s.commit()
