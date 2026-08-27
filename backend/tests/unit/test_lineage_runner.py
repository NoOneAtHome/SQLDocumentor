"""Lineage phase: engine results -> snapshot rows (edges, pseudo objects, issues)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from sqldoc.config.schema import DatabaseCfg
from sqldoc.lineage.runner import run_lineage
from sqldoc.mssql.catalog import RawDatabase
from sqldoc.scan.progress import ScanProgress
from sqldoc.scope.cascade import Closure
from sqldoc.store import models as m
from sqldoc.store.db import Database
from sqldoc.store.writer import SnapshotWriter

DB = "AW"
CUSTOMER, PERSON, VIEW, PROC, ARCHIVE, TRIG, FN = 1, 2, 3, 4, 5, 6, 7


def obj(object_id, schema, name, type_, parent=None):
    return dict(
        object_id=object_id,
        schema_name=schema,
        name=name,
        type=type_,
        type_desc=type_,
        create_date=None,
        modify_date=None,
        parent_object_id=parent,
    )


def col(object_id, column_id, name, **kw):
    row = dict(
        object_id=object_id,
        column_id=column_id,
        name=name,
        type_name="int",
        system_type_name="int",
        type_schema="sys",
        is_user_defined=False,
        max_length=4,
        precision=10,
        scale=0,
        is_nullable=False,
        is_identity=False,
        is_computed=False,
        computed_definition=None,
        is_persisted=None,
        default_name=None,
        default_definition=None,
        collation_name=None,
        seed_value=None,
        increment_value=None,
        is_rowguidcol=False,
        generated_always_type=0,
    )
    row.update(kw)
    return row


def module(object_id, definition):
    return dict(
        object_id=object_id,
        definition=definition,
        uses_ansi_nulls=True,
        uses_quoted_identifier=True,
        is_schema_bound=False,
        is_recompiled=False,
        null_on_null_input=False,
        execute_as_principal_id=None,
    )


VIEW_SQL = (
    "CREATE VIEW Sales.vCustomer AS SELECT c.CustomerID, p.FirstName AS GivenName "
    "FROM Sales.Customer c JOIN Person.Person p ON p.BusinessEntityID = c.PersonID"
)
PROC_SQL = (
    "CREATE PROCEDURE Sales.uspLoad AS BEGIN "
    "SELECT c.CustomerID AS Id INTO #t FROM Sales.Customer c "
    "INSERT INTO Sales.Archive (Id) SELECT t.Id FROM #t t "
    "EXEC dbo.uspMissing EXEC(@sql) "
    "SELECT a.Id AS Out FROM Sales.Archive a END"
)
TRIG_SQL = (
    "CREATE TRIGGER Sales.trCustomer ON Sales.Customer AFTER INSERT AS BEGIN "
    "INSERT INTO Sales.Archive (Id) SELECT inserted.CustomerID FROM inserted END"
)
FN_SQL = (
    "CREATE FUNCTION Sales.fnMax() RETURNS int AS BEGIN "
    "RETURN (SELECT MAX(CustomerID) FROM Sales.Customer) END"
)


@pytest.fixture
def scanned(tmp_path):
    db = Database.open(tmp_path / "l.sqlite")
    raw = RawDatabase(name=DB, info={})
    raw.objects = [
        obj(CUSTOMER, "Sales", "Customer", "U"),
        obj(PERSON, "Person", "Person", "U"),
        obj(VIEW, "Sales", "vCustomer", "V"),
        obj(PROC, "Sales", "uspLoad", "P"),
        obj(ARCHIVE, "Sales", "Archive", "U"),
        obj(TRIG, "Sales", "trCustomer", "TR", parent=CUSTOMER),
        obj(FN, "Sales", "fnMax", "FN"),
    ]
    raw.columns = [
        col(CUSTOMER, 1, "CustomerID"),
        col(CUSTOMER, 2, "PersonID"),
        col(CUSTOMER, 3, "Doubled", is_computed=True, computed_definition="([CustomerID]*(2))"),
        col(PERSON, 1, "BusinessEntityID"),
        col(PERSON, 2, "FirstName"),
        col(VIEW, 1, "CustomerID"),
        col(VIEW, 2, "GivenName"),
        col(ARCHIVE, 1, "Id"),
    ]
    raw.modules = [
        module(VIEW, VIEW_SQL),
        module(PROC, PROC_SQL),
        module(TRIG, TRIG_SQL),
        module(FN, FN_SQL),
    ]
    raw.triggers = [
        dict(
            object_id=TRIG,
            name="trCustomer",
            parent_id=CUSTOMER,
            type_desc="SQL_TRIGGER",
            is_disabled=False,
            is_instead_of_trigger=False,
            events="INSERT",
        )
    ]
    closure = Closure(
        scope={(DB, i): "in_scope" for i in (CUSTOMER, PERSON, VIEW, PROC, ARCHIVE, TRIG, FN)}
    )
    progress = ScanProgress(scan_id=0)
    with db.session() as s:
        scan = m.Scan(connection_name="c", status="running", started_at=datetime.now(UTC))
        s.add(scan)
        s.flush()
        w = SnapshotWriter(s, scan.id, "c")
        w.write_database(raw, DatabaseCfg(name=DB, schemas=["Sales"]))
        w.write_objects(raw, closure)
        w.write_details(raw)
        s.commit()
        run_lineage(s, w, {DB: raw}, progress)
        s.commit()
        return db, w, scan.id, progress


def rows(db, model, scan_id):
    with db.session() as s:
        return s.execute(select(model).where(model.scan_id == scan_id)).scalars().all()


def named_edges(db, scan_id):
    with db.session() as s:
        out = set()
        for e in s.execute(
            select(m.ColumnLineage).where(m.ColumnLineage.scan_id == scan_id)
        ).scalars():
            src_obj = s.get(m.DbObject, e.source_object_id) if e.source_object_id else None
            src_col = s.get(m.Column, e.source_column_id) if e.source_column_id else None
            tgt_obj = s.get(m.DbObject, e.target_object_id)
            tgt_col = s.get(m.Column, e.target_column_id)
            out.add(
                (
                    f"{src_obj.schema_name}.{src_obj.name}" if src_obj else None,
                    src_col.name if src_col else e.source_column_name,
                    f"{tgt_obj.schema_name}.{tgt_obj.name}",
                    tgt_col.name,
                    e.confidence,
                    e.transform,
                    e.via,
                )
            )
        return out


def test_view_edges_persisted(scanned):
    db, _, scan_id, _ = scanned
    edges = named_edges(db, scan_id)
    assert (
        "Sales.Customer",
        "CustomerID",
        "Sales.vCustomer",
        "CustomerID",
        "exact",
        "passthrough",
        None,
    ) in edges
    assert (
        "Person.Person",
        "FirstName",
        "Sales.vCustomer",
        "GivenName",
        "exact",
        "passthrough",
        None,
    ) in edges


def test_proc_temp_table_pseudo_object_and_edges(scanned):
    db, w, scan_id, _ = scanned
    objs = {o.name: o for o in rows(db, m.DbObject, scan_id)}
    temp = objs["#t"]
    assert temp.kind == "temp_table" and temp.parent_object_id == w.object_id(DB, PROC)
    assert temp.object_key == "c|AW|Sales|uspLoad|#t"
    edges = named_edges(db, scan_id)
    assert ("Sales.Customer", "CustomerID", "Sales.#t", "Id", "exact", "passthrough", None) in edges
    assert ("Sales.#t", "Id", "Sales.Archive", "Id", "exact", "temp", None) in edges
    with db.session() as s:
        via = (
            s.execute(
                select(m.ColumnLineage.via_object_id).where(
                    m.ColumnLineage.scan_id == scan_id,
                    m.ColumnLineage.target_object_id == w.object_id(DB, ARCHIVE),
                )
            )
            .scalars()
            .all()
        )
    assert w.object_id(DB, PROC) in via


def test_proc_result_set_pseudo_columns(scanned):
    db, w, scan_id, _ = scanned
    with db.session() as s:
        cols = (
            s.execute(select(m.Column).where(m.Column.object_id == w.object_id(DB, PROC)))
            .scalars()
            .all()
        )
    assert [(c.name, c.column_kind, c.resultset_index) for c in cols] == [("Out", "resultset", 0)]
    assert (
        "Sales.Archive",
        "Id",
        "Sales.uspLoad",
        "Out",
        "exact",
        "passthrough",
        None,
    ) in named_edges(db, scan_id)


def test_parsed_object_dependencies_and_issues(scanned):
    db, w, scan_id, _ = scanned
    with db.session() as s:
        deps = (
            s.execute(select(m.ObjectDependency).where(m.ObjectDependency.scan_id == scan_id))
            .scalars()
            .all()
        )
        objs = {
            o.id: o
            for o in s.execute(select(m.DbObject).where(m.DbObject.scan_id == scan_id)).scalars()
        }
    parsed = {
        (
            objs[d.source_object_id].name,
            d.edge_kind,
            objs[d.target_object_id].name if d.target_object_id else d.referenced_name,
            d.resolution,
        )
        for d in deps
    }
    assert ("vCustomer", "parsed_read", "Customer", "resolved") in parsed
    assert ("vCustomer", "parsed_read", "Person", "resolved") in parsed
    assert ("uspLoad", "parsed_write", "Archive", "resolved") in parsed
    assert ("uspLoad", "parsed_exec", "dbo.uspMissing", "unresolved") in parsed
    issues = rows(db, m.LineageIssue, scan_id)
    assert any(i.kind == "dynamic_sql" and i.object_id == w.object_id(DB, PROC) for i in issues)
    proc = next(o for o in objs.values() if o.name == "uspLoad")
    assert proc.has_dynamic_sql is True and proc.lineage_status == "partial"
    assert next(o for o in objs.values() if o.name == "vCustomer").lineage_status == "ok"
    assert next(o for o in objs.values() if o.name == "Customer").lineage_status == "n/a"


def test_trigger_and_scalar_function_and_computed_column(scanned):
    db, w, scan_id, _ = scanned
    edges = named_edges(db, scan_id)
    assert (
        "Sales.Customer",
        "CustomerID",
        "Sales.Archive",
        "Id",
        "exact",
        "passthrough",
        "inserted",
    ) in edges
    assert (
        "Sales.Customer",
        "CustomerID",
        "Sales.fnMax",
        "RETURN_VALUE",
        "inferred",
        "aggregate",
        None,
    ) in edges
    assert (
        "Sales.Customer",
        "CustomerID",
        "Sales.Customer",
        "Doubled",
        "inferred",
        "computed",
        None,
    ) in edges
    with db.session() as s:
        ret = (
            s.execute(select(m.Column).where(m.Column.object_id == w.object_id(DB, FN)))
            .scalars()
            .one()
        )
    assert ret.column_kind == "return_value" and ret.name == "RETURN_VALUE"


def test_progress_advanced_per_object(scanned):
    _, _, _, progress = scanned
    snap = progress.snapshot()
    assert snap["phase"] == "lineage" and snap["total"] == 4 and snap["current"] == 4
