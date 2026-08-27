"""Column lineage on the live AdventureWorks2022 database (Sales + dbo scope)."""

import json

import pytest
from sqlalchemy import select

from sqldoc.config.schema import AppConfig, DatabaseCfg
from sqldoc.scan.manager import ScanManager
from sqldoc.store import models as m
from sqldoc.store.db import Database

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def scanned(tmp_path_factory, aw_connection_cfg):
    conn = aw_connection_cfg.model_copy(
        update={"databases": [DatabaseCfg(name="AdventureWorks2022", schemas=["Sales", "dbo"])]}
    )
    db = Database.open(tmp_path_factory.mktemp("lineage") / "aw.sqlite")
    mgr = ScanManager(db, AppConfig(connections=[conn]))
    scan_id = mgr.start(conn.name)
    assert mgr.wait(scan_id, timeout=300)
    snap = mgr.progress(scan_id)
    assert snap["status"] == "succeeded", snap
    return db, scan_id


def edges(db, scan_id):
    with db.session() as s:
        objs = {
            o.id: o
            for o in s.execute(select(m.DbObject).where(m.DbObject.scan_id == scan_id)).scalars()
        }
        cols = {
            c.id: c
            for c in s.execute(select(m.Column).where(m.Column.scan_id == scan_id)).scalars()
        }
        out = set()
        for e in s.execute(
            select(m.ColumnLineage).where(m.ColumnLineage.scan_id == scan_id)
        ).scalars():
            src = objs.get(e.source_object_id)
            src_col = cols.get(e.source_column_id)
            tgt, tgt_col = objs[e.target_object_id], cols[e.target_column_id]
            out.add(
                (
                    f"{src.schema_name}.{src.name}" if src else None,
                    src_col.name if src_col else e.source_column_name,
                    f"{tgt.schema_name}.{tgt.name}",
                    tgt_col.name,
                    e.confidence,
                    e.via,
                )
            )
        return out, objs


def test_view_lineage_is_exact(scanned):
    db, scan_id = scanned
    e, _ = edges(db, scan_id)
    assert (
        "Person.Person",
        "FirstName",
        "Sales.vIndividualCustomer",
        "FirstName",
        "exact",
        None,
    ) in e
    assert (
        "Person.Address",
        "AddressLine1",
        "Sales.vIndividualCustomer",
        "AddressLine1",
        "exact",
        None,
    ) in e
    assert (
        "Person.PhoneNumberType",
        "Name",
        "Sales.vIndividualCustomer",
        "PhoneNumberType",
        "exact",
        None,
    ) in e
    assert (
        "Sales.SalesPerson",
        "SalesQuota",
        "Sales.vSalesPerson",
        "SalesQuota",
        "exact",
        None,
    ) in e


def test_multi_statement_tvf_and_trigger(scanned):
    db, scan_id = scanned
    e, _ = edges(db, scan_id)
    assert any(
        s == "Person.Person" and t == "dbo.ufnGetContactInformation" for s, _, t, _, _, _ in e
    )
    assert any(
        t == "Production.TransactionHistory" and via == "inserted" and s == "Sales.SalesOrderDetail"
        for s, _, t, _, _, via in e
    )


def test_proc_result_sets_trace_to_tables(scanned):
    db, scan_id = scanned
    e, objs = edges(db, scan_id)
    bom_targets = {(s, c) for s, c, t, _, _, _ in e if t == "dbo.uspGetBillOfMaterials"}
    assert any(s in ("Production.BillOfMaterials", "Production.Product") for s, _ in bom_targets), (
        bom_targets
    )
    proc = next(o for o in objs.values() if o.name == "uspGetBillOfMaterials")
    with db.session() as s:
        rs = (
            s.execute(
                select(m.Column).where(
                    m.Column.object_id == proc.id, m.Column.column_kind == "resultset"
                )
            )
            .scalars()
            .all()
        )
    assert {c.name for c in rs} >= {"ProductAssemblyID", "ComponentID", "ComponentDesc"}


def test_coverage_and_pivot_does_not_crash(scanned):
    db, scan_id = scanned
    with db.session() as s:
        scan = s.get(m.Scan, scan_id)
        summary = json.loads(scan.summary_json)
        statuses = dict(
            s.execute(
                select(m.DbObject.lineage_status, m.DbObject.id).where(
                    m.DbObject.scan_id == scan_id
                )
            ).all()
        )
        objs = (
            s.execute(
                select(m.DbObject).where(
                    m.DbObject.scan_id == scan_id, m.DbObject.definition.is_not(None)
                )
            )
            .scalars()
            .all()
        )
        pivot = next(o for o in objs if o.name == "vSalesPersonSalesByFiscalYears")
        issues = (
            s.execute(select(m.LineageIssue).where(m.LineageIssue.scan_id == scan_id))
            .scalars()
            .all()
        )
    assert summary["edges_column"] >= 140, summary
    ok = sum(1 for o in objs if o.lineage_status == "ok")
    assert ok / len(objs) >= 0.8, {
        o.name: o.lineage_status for o in objs if o.lineage_status != "ok"
    }
    assert pivot.lineage_status in ("ok", "partial", "failed")
    assert all(i.kind for i in issues)
    del statuses
