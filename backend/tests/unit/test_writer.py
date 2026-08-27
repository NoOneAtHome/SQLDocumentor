"""SnapshotWriter: raw catalog rows + closure -> snapshot tables."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from sqldoc.config.schema import DatabaseCfg
from sqldoc.mssql.catalog import RawDatabase
from sqldoc.scope.cascade import Closure, Edge, ExternalRef
from sqldoc.store import models as m
from sqldoc.store.db import Database
from sqldoc.store.writer import SnapshotWriter

DB = "AW"
CUSTOMER, VIEW, PERSON, FN, TRIG = 1, 2, 3, 4, 5


def obj(object_id, schema, name, type_, parent=None):
    return dict(
        object_id=object_id,
        schema_name=schema,
        name=name,
        type=type_,
        type_desc=type_,
        create_date=datetime(2020, 1, 1),
        modify_date=datetime(2021, 1, 1),
        parent_object_id=parent,
    )


def col(object_id, column_id, name, type_name="int", **kw):
    row = dict(
        object_id=object_id,
        column_id=column_id,
        name=name,
        type_name=type_name,
        system_type_name=type_name,
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


@pytest.fixture
def raw() -> RawDatabase:
    r = RawDatabase(
        name=DB, info=dict(database_id=5, name=DB, collation_name="Latin1", compatibility_level=160)
    )
    r.objects = [
        obj(CUSTOMER, "Sales", "Customer", "U"),
        obj(VIEW, "Sales", "vCustomer", "V"),
        obj(PERSON, "Person", "Person", "U"),
        obj(FN, "dbo", "ufnUnused", "FN"),  # not in closure -> must not be written
        obj(TRIG, "Sales", "trCustomer", "TR", parent=CUSTOMER),
    ]
    r.columns = [
        col(CUSTOMER, 1, "CustomerID", is_identity=True),
        col(CUSTOMER, 2, "PersonID", is_nullable=True),
        col(
            CUSTOMER,
            3,
            "AccountNumber",
            "varchar",
            max_length=10,
            is_computed=True,
            computed_definition="(isnull('AW'+[dbo].[ufnLeadingZeros]([CustomerID]),''))",
        ),
        col(VIEW, 1, "CustomerID"),
        col(PERSON, 1, "BusinessEntityID"),
        col(PERSON, 2, "FirstName", "nvarchar", max_length=100),
        col(FN, 1, "x"),
    ]
    r.parameters = [
        dict(
            object_id=FN,
            parameter_id=0,
            name="",
            type_name="int",
            system_type_name="int",
            is_user_defined=False,
            max_length=4,
            precision=10,
            scale=0,
            is_output=True,
            has_default_value=False,
            default_value=None,
            is_readonly=False,
            is_table_type=False,
        ),
    ]
    r.indexes = [
        dict(
            object_id=CUSTOMER,
            index_id=1,
            name="PK_Customer",
            type=1,
            type_desc="CLUSTERED",
            is_unique=True,
            is_primary_key=True,
            is_unique_constraint=False,
            has_filter=False,
            filter_definition=None,
            fill_factor=0,
            is_disabled=False,
            is_padded=False,
            data_space_name="PRIMARY",
            data_space_type="FG",
        ),
        dict(
            object_id=CUSTOMER,
            index_id=2,
            name="IX_Person",
            type=2,
            type_desc="NONCLUSTERED",
            is_unique=False,
            is_primary_key=False,
            is_unique_constraint=False,
            has_filter=False,
            filter_definition=None,
            fill_factor=0,
            is_disabled=False,
            is_padded=False,
            data_space_name="PRIMARY",
            data_space_type="FG",
        ),
    ]
    r.index_columns = [
        dict(
            object_id=CUSTOMER,
            index_id=1,
            index_column_id=1,
            column_id=1,
            column_name="CustomerID",
            key_ordinal=1,
            is_descending_key=False,
            is_included_column=False,
            partition_ordinal=0,
        ),
        dict(
            object_id=CUSTOMER,
            index_id=2,
            index_column_id=1,
            column_id=2,
            column_name="PersonID",
            key_ordinal=1,
            is_descending_key=False,
            is_included_column=False,
            partition_ordinal=0,
        ),
        dict(
            object_id=CUSTOMER,
            index_id=2,
            index_column_id=2,
            column_id=3,
            column_name="AccountNumber",
            key_ordinal=0,
            is_descending_key=False,
            is_included_column=True,
            partition_ordinal=0,
        ),
    ]
    r.foreign_keys = [
        dict(
            object_id=900,
            name="FK_Customer_Person",
            parent_object_id=CUSTOMER,
            referenced_object_id=PERSON,
            key_index_id=1,
            delete_referential_action_desc="NO_ACTION",
            update_referential_action_desc="CASCADE",
            is_disabled=False,
            is_not_trusted=False,
            is_not_for_replication=False,
        ),
    ]
    r.foreign_key_columns = [
        dict(
            constraint_object_id=900,
            constraint_column_id=1,
            parent_object_id=CUSTOMER,
            parent_column_id=2,
            parent_column="PersonID",
            referenced_object_id=PERSON,
            referenced_column_id=1,
            referenced_column="BusinessEntityID",
        ),
    ]
    r.check_constraints = [
        dict(
            object_id=901,
            name="CK_Customer_ID",
            parent_object_id=CUSTOMER,
            parent_column_id=1,
            definition="([CustomerID]>(0))",
            is_disabled=False,
            is_not_trusted=False,
        ),
    ]
    r.extended_properties = [
        dict(class_=None, major_id=CUSTOMER, minor_id=0, name="MS_Description", value="Customers.")
        | {"class": 1},
        dict(major_id=CUSTOMER, minor_id=1, name="MS_Description", value="PK.") | {"class": 1},
        dict(major_id=CUSTOMER, minor_id=2, name="MS_Description", value="Index doc.")
        | {"class": 7},
        dict(major_id=FN, minor_id=0, name="MS_Description", value="Return doc.") | {"class": 2},
    ]
    r.modules = [
        dict(
            object_id=VIEW,
            definition="CREATE VIEW Sales.vCustomer AS SELECT CustomerID FROM Sales.Customer",
            uses_ansi_nulls=True,
            uses_quoted_identifier=True,
            is_schema_bound=False,
            is_recompiled=False,
            null_on_null_input=False,
            execute_as_principal_id=None,
        ),
        dict(
            object_id=TRIG,
            definition="CREATE TRIGGER ...",
            uses_ansi_nulls=True,
            uses_quoted_identifier=True,
            is_schema_bound=False,
            is_recompiled=False,
            null_on_null_input=False,
            execute_as_principal_id=None,
        ),
    ]
    r.triggers = [
        dict(
            object_id=TRIG,
            name="trCustomer",
            parent_id=CUSTOMER,
            type_desc="SQL_TRIGGER",
            is_disabled=False,
            is_instead_of_trigger=False,
            events="INSERT,UPDATE",
        ),
    ]
    return r


@pytest.fixture
def closure() -> Closure:
    ext = ExternalRef(None, "OtherDb", "dbo", "Remote")
    return Closure(
        scope={
            (DB, CUSTOMER): "in_scope",
            (DB, VIEW): "in_scope",
            (DB, PERSON): "cascaded",
            (DB, TRIG): "in_scope",
        },
        edges=[
            Edge(source=(DB, VIEW), target=(DB, CUSTOMER), kind="catalog"),
            Edge(source=(DB, CUSTOMER), target=(DB, PERSON), kind="fk", fk_id=900),
            Edge(source=(DB, TRIG), target=(DB, CUSTOMER), kind="trigger"),
            Edge(
                source=(DB, VIEW),
                target=None,
                kind="catalog",
                resolution="external",
                external_key=ext.key,
                referenced_name="Remote",
            ),
            Edge(
                source=(DB, VIEW),
                target=None,
                kind="catalog",
                resolution="ambiguous",
                referenced_name="value",
                is_ambiguous=True,
            ),
        ],
        externals={ext.key: ext},
    )


@pytest.fixture
def db(tmp_path):
    return Database.open(tmp_path / "w.sqlite")


@pytest.fixture
def written(db, raw, closure):
    with db.session() as s:
        scan = m.Scan(connection_name="local", status="running", started_at=datetime.now(UTC))
        s.add(scan)
        s.flush()
        w = SnapshotWriter(s, scan_id=scan.id, connection_name="local")
        w.write_database(
            raw, DatabaseCfg(name=DB, schemas=["Sales"]), permissions={"view_definition": True}
        )
        w.write_objects(raw, closure)
        w.write_externals(closure)
        w.write_details(raw)
        w.write_dependencies(closure)
        s.commit()
        return db, w, scan.id


def all_rows(db, model):
    with db.session() as s:
        return s.execute(select(model)).scalars().all()


def test_objects_written_only_for_closure_plus_externals(written):
    db, w, _ = written
    objs = {o.name: o for o in all_rows(db, m.DbObject)}
    assert set(objs) == {"Customer", "vCustomer", "Person", "trCustomer", "Remote"}
    assert objs["Customer"].scope == "in_scope" and objs["Customer"].kind == "table"
    assert objs["Person"].scope == "cascaded"
    assert objs["Remote"].scope == "external" and objs["Remote"].kind == "external"
    assert objs["Remote"].database_name == "OtherDb" and objs["Remote"].schema_name == "dbo"
    assert objs["Customer"].object_key == "local|AW|Sales|Customer"
    assert objs["Remote"].object_key == "external||OtherDb|dbo|Remote"
    assert objs["Customer"].description == "Customers."
    assert objs["Customer"].database_name == DB
    assert objs["trCustomer"].parent_object_id == objs["Customer"].id
    assert objs["trCustomer"].trigger_events == "INSERT,UPDATE"
    assert objs["vCustomer"].definition.startswith("CREATE VIEW")
    assert objs["Customer"].lineage_status == "n/a"
    assert objs["vCustomer"].lineage_status == "pending"


def test_columns_types_descriptions_and_keys(written):
    db, w, _ = written
    cols = {(c.object_id, c.name): c for c in all_rows(db, m.Column)}
    customer_id = w.object_id(DB, CUSTOMER)
    assert (customer_id, "CustomerID") in cols
    assert cols[(customer_id, "CustomerID")].description == "PK."
    assert cols[(customer_id, "CustomerID")].is_identity is True
    assert cols[(customer_id, "AccountNumber")].type_display == "varchar(10)"
    assert cols[(customer_id, "AccountNumber")].computed_definition.startswith("(isnull")
    assert cols[(customer_id, "CustomerID")].column_key == "local|AW|Sales|Customer|CustomerID"
    assert w.column_id(DB, CUSTOMER, 1) == cols[(customer_id, "CustomerID")].id
    assert all(c.object_id != w.object_id(DB, FN) for c in cols.values())  # FN not written at all
    assert w.object_id(DB, FN) is None


def test_indexes_with_columns_and_descriptions(written):
    db, w, _ = written
    idx = {i.name: i for i in all_rows(db, m.IndexDef)}
    assert idx["PK_Customer"].is_primary_key
    assert idx["IX_Person"].description == "Index doc."
    ic = [c for c in all_rows(db, m.IndexColumn) if c.index_id == idx["IX_Person"].id]
    assert [(c.column_name, c.is_included) for c in sorted(ic, key=lambda c: c.id)] == [
        ("PersonID", False),
        ("AccountNumber", True),
    ]
    assert all(c.column_id is not None for c in ic)


def test_foreign_keys_and_checks(written):
    db, w, _ = written
    fk = all_rows(db, m.ForeignKeyDef)[0]
    assert fk.parent_object_id == w.object_id(DB, CUSTOMER)
    assert fk.referenced_object_id == w.object_id(DB, PERSON)
    assert fk.update_action == "CASCADE"
    fkc = all_rows(db, m.ForeignKeyColumn)[0]
    assert fkc.parent_column_id == w.column_id(DB, CUSTOMER, 2)
    assert fkc.referenced_column_id == w.column_id(DB, PERSON, 1)
    ck = all_rows(db, m.CheckConstraintDef)[0]
    assert ck.column_id == w.column_id(DB, CUSTOMER, 1) and ck.definition.startswith(
        "([CustomerID]"
    )


def test_dependency_edges_map_to_snapshot_ids(written):
    db, w, _ = written
    deps = all_rows(db, m.ObjectDependency)
    by = {(d.source_object_id, d.target_object_id, d.edge_kind): d for d in deps}
    view, customer, person, trig = (w.object_id(DB, x) for x in (VIEW, CUSTOMER, PERSON, TRIG))
    remote = w.external_id("external||OtherDb|dbo|Remote")
    assert (view, customer, "catalog") in by
    assert (customer, person, "fk") in by
    assert (trig, customer, "trigger") in by
    assert by[(view, remote, "catalog")].resolution == "external"
    ambiguous = [d for d in deps if d.resolution == "ambiguous"]
    assert len(ambiguous) == 1 and ambiguous[0].target_object_id is None
    assert ambiguous[0].referenced_name == "value"


def test_database_row(written):
    db, _, scan_id = written
    row = all_rows(db, m.SnapshotDatabase)[0]
    assert row.scan_id == scan_id and row.name == DB and row.is_configured
    assert row.has_view_definition is True
    assert row.selected_schemas_json == '["Sales"]'
