"""Full scan of AdventureWorks2022 (Sales schema) into a fresh SQLite snapshot."""

import pytest
from sqlalchemy import func, select

from sqldoc.config.schema import AppConfig, ScanOptions
from sqldoc.scan.manager import ScanManager
from sqldoc.store import models as m
from sqldoc.store.db import Database

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def scanned(tmp_path_factory, aw_connection_cfg):
    db = Database.open(tmp_path_factory.mktemp("scan") / "aw.sqlite")
    cfg = AppConfig(connections=[aw_connection_cfg], scan=ScanOptions(parse_lineage=False))
    mgr = ScanManager(db, cfg)
    scan_id = mgr.start(aw_connection_cfg.name)
    assert mgr.wait(scan_id, timeout=120)
    return db, mgr, scan_id


def test_scan_succeeds_with_summary(scanned):
    db, mgr, scan_id = scanned
    snap = mgr.progress(scan_id)
    assert snap["status"] == "succeeded", snap
    with db.session() as s:
        scan = s.get(m.Scan, scan_id)
    assert scan.server_version.startswith("16.")
    assert scan.auth_scheme == "SQL" and scan.driver == "pymssql"
    assert scan.finished_at is not None
    assert '"tables"' in scan.summary_json
    assert db.latest_scan_id(s, aw_name(scanned)) == scan_id


def aw_name(scanned):
    return "test-aw"


def test_objects_and_scopes(scanned):
    db, _, scan_id = scanned
    with db.session() as s:
        objs = s.execute(select(m.DbObject).where(m.DbObject.scan_id == scan_id)).scalars().all()
    by_name = {f"{o.schema_name}.{o.name}": o for o in objs}
    assert by_name["Sales.Customer"].scope == "in_scope"
    assert by_name["Person.Person"].scope == "cascaded"
    assert by_name["dbo.ufnLeadingZeros"].scope == "cascaded"
    assert (
        by_name["Sales.iduSalesOrderDetail"].parent_object_id
        == by_name["Sales.SalesOrderDetail"].id
    )
    assert (
        by_name["Sales.vIndividualCustomer"].definition.upper().lstrip().startswith("CREATE VIEW")
    )
    assert by_name["Sales.Customer"].description  # MS_Description present in AdventureWorks
    assert not [o for o in objs if o.kind == "external"]
    assert {o.lineage_status for o in objs} == {"n/a", "skipped"}  # lineage was disabled


def test_details_and_stats(scanned):
    db, _, scan_id = scanned
    with db.session() as s:
        customer = s.execute(
            select(m.DbObject).where(
                m.DbObject.scan_id == scan_id,
                m.DbObject.name == "Customer",
                m.DbObject.schema_name == "Sales",
            )
        ).scalar_one()
        cols = s.execute(select(m.Column).where(m.Column.object_id == customer.id)).scalars().all()
        assert {c.name for c in cols} >= {"CustomerID", "PersonID", "AccountNumber"}
        account = next(c for c in cols if c.name == "AccountNumber")
        assert account.is_computed and account.type_display == "varchar(10)"
        ts = s.execute(
            select(m.TableStats).where(m.TableStats.object_id == customer.id)
        ).scalar_one()
        assert ts.row_count == 19820
        n_usage = s.execute(
            select(func.count()).select_from(m.IndexUsage).where(m.IndexUsage.scan_id == scan_id)
        ).scalar()
        assert n_usage > 0
        fks = (
            s.execute(
                select(m.ForeignKeyDef).where(m.ForeignKeyDef.parent_object_id == customer.id)
            )
            .scalars()
            .all()
        )
        assert {fk.name for fk in fks} >= {
            "FK_Customer_Person_PersonID",
            "FK_Customer_Store_StoreID",
        }
        deps = (
            s.execute(select(m.ObjectDependency).where(m.ObjectDependency.scan_id == scan_id))
            .scalars()
            .all()
        )
        assert any(d.edge_kind == "fk" for d in deps) and any(
            d.edge_kind == "trigger" for d in deps
        )
        assert any(d.resolution == "ambiguous" for d in deps)
        warnings = (
            s.execute(select(m.ScanWarning).where(m.ScanWarning.scan_id == scan_id)).scalars().all()
        )
        assert warnings == []


def test_second_scan_becomes_latest(scanned):
    db, mgr, first = scanned
    second = mgr.start("test-aw")
    assert mgr.wait(second, timeout=120)
    with db.session() as s:
        assert db.latest_scan_id(s, "test-aw") == second
