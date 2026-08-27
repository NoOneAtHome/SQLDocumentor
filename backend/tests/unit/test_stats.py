"""StatsExtractor degrades per query; SnapshotWriter derives the flags."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from sqldoc.config.schema import DatabaseCfg
from sqldoc.mssql.catalog import RawDatabase
from sqldoc.mssql.stats import RawStats, StatsExtractor
from sqldoc.scope.cascade import Closure
from sqldoc.store import models as m
from sqldoc.store.db import Database
from sqldoc.store.writer import SnapshotWriter


class FakeClient:
    """Routes query text to canned rows or exceptions by DMV name."""

    def __init__(self, routes):
        self.routes, self.executed = routes, []

    def query(self, sql, params=None):
        for needle, result in self.routes.items():
            if needle in sql:
                self.executed.append(needle)
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unexpected query: {sql[:60]}")


ROUTES = {
    "dm_db_partition_stats": [
        dict(
            object_id=1,
            row_count=10,
            data_kb=16,
            index_kb=8,
            reserved_kb=32,
            partition_count=1,
            is_heap=0,
            compression_min="NONE",
            compression_max="PAGE",
        )
    ],
    "dm_db_index_usage_stats": [
        dict(
            object_id=1,
            index_id=2,
            user_seeks=5,
            user_scans=0,
            user_lookups=0,
            user_updates=7,
            last_user_seek=datetime(2026, 1, 1),
            last_user_scan=None,
            last_user_lookup=None,
            last_user_update=None,
        )
    ],
    "dm_exec_procedure_stats": [
        dict(
            object_id=9,
            kind="procedure",
            execution_count=4,
            total_elapsed_us=4000,
            min_elapsed_us=500,
            max_elapsed_us=2000,
            total_cpu_us=3000,
            total_logical_reads=40,
            last_execution_time=datetime(2026, 1, 2),
            cached_time=datetime(2025, 12, 1),
        )
    ],
    "dm_db_missing_index_details": [
        dict(
            object_id=1,
            index_handle=77,
            equality_columns="[PersonID]",
            inequality_columns="[ModifiedDate]",
            included_columns="[AccountNumber]",
            unique_compiles=3,
            user_seeks=100,
            user_scans=0,
            last_user_seek=datetime(2026, 1, 3),
            avg_total_user_cost=12.5,
            avg_user_impact=80.0,
        )
    ],
}


def test_collects_all_four_stat_families():
    raw = StatsExtractor(FakeClient(ROUTES)).collect()
    assert raw.table_stats[0]["row_count"] == 10
    assert raw.index_usage[0]["user_seeks"] == 5
    assert raw.proc_stats[0]["execution_count"] == 4
    assert raw.missing_indexes[0]["index_handle"] == 77
    assert raw.warnings == []


def test_failed_query_becomes_warning_and_others_still_collected():
    routes = dict(ROUTES)
    routes["dm_db_index_usage_stats"] = RuntimeError("VIEW DATABASE STATE permission denied")
    raw = StatsExtractor(FakeClient(routes)).collect()
    assert raw.index_usage == []
    assert raw.table_stats and raw.proc_stats and raw.missing_indexes
    assert len(raw.warnings) == 1
    w = raw.warnings[0]
    assert w.code == "stats_unavailable" and w.query == "index_usage"
    assert "permission denied" in w.message


def test_known_missing_permissions_skip_queries_without_running_them():
    client = FakeClient(ROUTES)
    raw = StatsExtractor(
        client, permissions={"view_server_state": False, "view_database_state": True}
    ).collect()
    assert "dm_exec_procedure_stats" not in client.executed
    assert "dm_db_missing_index_details" not in client.executed
    assert (
        "dm_db_partition_stats" in client.executed and "dm_db_index_usage_stats" in client.executed
    )
    codes = sorted((w.code, w.query) for w in raw.warnings)
    assert codes == [
        ("permission_missing", "missing_indexes"),
        ("permission_missing", "proc_stats"),
    ]


# --- writer derivations ----------------------------------------------------------------

DB = "AW"


def _index(object_id, index_id, name, type_code, pk=False, uq=False):
    return dict(
        object_id=object_id,
        index_id=index_id,
        name=name,
        type=type_code,
        type_desc="X",
        is_unique=pk or uq,
        is_primary_key=pk,
        is_unique_constraint=uq,
        has_filter=False,
        filter_definition=None,
        fill_factor=0,
        is_disabled=False,
        is_padded=False,
        data_space_name="PRIMARY",
        data_space_type="FG",
    )


@pytest.fixture
def written(tmp_path):
    db = Database.open(tmp_path / "s.sqlite")
    raw = RawDatabase(name=DB, info={})
    raw.objects = [
        dict(
            object_id=1,
            schema_name="Sales",
            name="Customer",
            type="U",
            type_desc="U",
            create_date=None,
            modify_date=None,
            parent_object_id=None,
        ),
        dict(
            object_id=9,
            schema_name="Sales",
            name="uspX",
            type="P",
            type_desc="P",
            create_date=None,
            modify_date=None,
            parent_object_id=None,
        ),
    ]
    raw.indexes = [
        _index(1, 1, "PK_Customer", 1, pk=True),
        _index(1, 2, "IX_Person", 2),
        _index(1, 3, "IX_Unused", 2),
        _index(1, 4, "UQ_Account", 2, uq=True),
    ]
    closure = Closure(scope={(DB, 1): "in_scope", (DB, 9): "in_scope"})
    stats = RawStats(
        table_stats=ROUTES["dm_db_partition_stats"],
        index_usage=ROUTES["dm_db_index_usage_stats"],
        proc_stats=ROUTES["dm_exec_procedure_stats"],
        missing_indexes=ROUTES["dm_db_missing_index_details"],
    )
    with db.session() as s:
        scan = m.Scan(connection_name="c", status="running", started_at=datetime.now(UTC))
        s.add(scan)
        s.flush()
        w = SnapshotWriter(s, scan.id, "c")
        w.write_database(raw, DatabaseCfg(name=DB, schemas=["Sales"]))
        w.write_objects(raw, closure)
        w.write_details(raw)
        w.write_stats(DB, stats)
        s.commit()
        return db, w


def test_table_stats_with_mixed_compression(written):
    db, w = written
    with db.session() as s:
        ts = s.execute(select(m.TableStats)).scalar_one()
    assert ts.object_id == w.object_id(DB, 1)
    assert ts.row_count == 10 and ts.data_kb == 16 and ts.index_kb == 8
    assert ts.compression == "MIXED" and ts.is_heap is False


def test_index_usage_rows_for_every_index_and_unused_flag(written):
    db, w = written
    with db.session() as s:
        rows = s.execute(select(m.IndexUsage, m.IndexDef.name).join(m.IndexDef)).all()
    by_name = {name: usage for usage, name in rows}
    assert set(by_name) == {"PK_Customer", "IX_Person", "IX_Unused", "UQ_Account"}
    assert by_name["IX_Person"].user_seeks == 5 and by_name["IX_Person"].is_unused is False
    assert by_name["IX_Unused"].user_seeks == 0 and by_name["IX_Unused"].is_unused is True
    assert by_name["PK_Customer"].is_unused is False  # PKs/unique constraints are never "unused"
    assert by_name["UQ_Account"].is_unused is False


def test_proc_stats_average(written):
    db, w = written
    with db.session() as s:
        ps = s.execute(select(m.ProcStats)).scalar_one()
    assert ps.object_id == w.object_id(DB, 9)
    assert ps.avg_elapsed_us == 1000


def test_missing_index_measure_and_ddl(written):
    db, w = written
    with db.session() as s:
        mi = s.execute(select(m.MissingIndex)).scalar_one()
    assert mi.improvement_measure == pytest.approx(12.5 * 80.0 * 100)
    assert mi.suggested_ddl == (
        "CREATE NONCLUSTERED INDEX [IX_Customer_PersonID_ModifiedDate] ON [Sales].[Customer] "
        "([PersonID], [ModifiedDate]) INCLUDE ([AccountNumber]);"
    )
