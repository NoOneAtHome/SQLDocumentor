"""Shared fixtures for the API/repo/graph unit tests.

Builds one realistic, fully populated snapshot (via ``SnapshotWriter`` plus direct
inserts for lineage, stats and annotations), wraps it in a ``Runtime`` with a stub
scan runner and exposes a ``TestClient``. This module has no tests of its own; the
``test_api_`` prefix keeps it inside the API layer's file ownership.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sqldoc.api.app import create_app
from sqldoc.config.schema import (
    AppConfig,
    AuthCfg,
    ConnectionCfg,
    DatabaseCfg,
    ScanOptions,
    StorageCfg,
)
from sqldoc.mssql.catalog import RawDatabase
from sqldoc.runtime import Runtime
from sqldoc.scan.manager import ScanManager
from sqldoc.scope.cascade import Closure, Edge, ExternalRef
from sqldoc.store import models as m
from sqldoc.store.db import Database
from sqldoc.store.models import utcnow
from sqldoc.store.repo import scan_counts
from sqldoc.store.writer import SnapshotWriter

CONN = "local"
DB = "AW"
CUSTOMER, VIEW, PERSON, ADDRESS, PROC, TRIG, FN, UNUSED_FN = 1, 2, 3, 4, 5, 6, 7, 8
REMOTE = ExternalRef(None, "OtherDb", "dbo", "Remote")

CONFIG_YAML = """
version: 1
storage: { sqlite_path: api.sqlite }
connections:
  - name: local
    host: localhost
    port: 1433
    auth: { mode: sql, username: sa, password: "hunter2" }
    driver: pymssql
    databases:
      - { name: AW, schemas: [Sales] }
  - name: dw
    host: sqlprod01
    auth: { mode: integrated }
    databases:
      - { name: DW, schemas: [dbo] }
"""


# -- raw catalog row helpers -----------------------------------------------------------


def obj(object_id, schema, name, type_, parent=None):
    return dict(
        object_id=object_id,
        schema_name=schema,
        name=name,
        type=type_,
        type_desc=type_,
        create_date=datetime(2020, 1, 1),
        modify_date=datetime(2021, 1, 1) + timedelta(days=object_id),
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


def param(object_id, parameter_id, name, type_name="int", **kw):
    row = dict(
        object_id=object_id,
        parameter_id=parameter_id,
        name=name,
        type_name=type_name,
        system_type_name=type_name,
        is_user_defined=False,
        max_length=4,
        precision=10,
        scale=0,
        is_output=parameter_id == 0,
        has_default_value=False,
        default_value=None,
        is_readonly=False,
        is_table_type=False,
    )
    row.update(kw)
    return row


def idx(object_id, index_id, name, type_code, type_desc, unique, pk, uq=False):
    return dict(
        object_id=object_id,
        index_id=index_id,
        name=name,
        type=type_code,
        type_desc=type_desc,
        is_unique=unique,
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


def ic(object_id, index_id, index_column_id, column_id, column_name, key_ordinal, included=False):
    return dict(
        object_id=object_id,
        index_id=index_id,
        index_column_id=index_column_id,
        column_id=column_id,
        column_name=column_name,
        key_ordinal=key_ordinal,
        is_descending_key=False,
        is_included_column=included,
        partition_ordinal=0,
    )


def fk(fk_id, name, parent, referenced):
    return dict(
        object_id=fk_id,
        name=name,
        parent_object_id=parent,
        referenced_object_id=referenced,
        key_index_id=1,
        delete_referential_action_desc="NO_ACTION",
        update_referential_action_desc="NO_ACTION",
        is_disabled=False,
        is_not_trusted=False,
        is_not_for_replication=False,
    )


def fkc(fk_id, ordinal, parent, parent_col_id, parent_col, referenced, ref_col_id, ref_col):
    return dict(
        constraint_object_id=fk_id,
        constraint_column_id=ordinal,
        parent_object_id=parent,
        parent_column_id=parent_col_id,
        parent_column=parent_col,
        referenced_object_id=referenced,
        referenced_column_id=ref_col_id,
        referenced_column=ref_col,
    )


def mod(object_id, definition):
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


def ep(klass, major, minor, value):
    return {
        "class": klass,
        "major_id": major,
        "minor_id": minor,
        "name": "MS_Description",
        "value": value,
    }


def raw_database() -> RawDatabase:
    r = RawDatabase(
        name=DB, info=dict(database_id=5, name=DB, collation_name="Latin1", compatibility_level=160)
    )
    r.objects = [
        obj(CUSTOMER, "Sales", "Customer", "U"),
        obj(VIEW, "Sales", "vCustomer", "V"),
        obj(PERSON, "Person", "Person", "U"),
        obj(ADDRESS, "Person", "Address", "U"),
        obj(PROC, "Sales", "uspUpdateCustomer", "P"),
        obj(TRIG, "Sales", "trCustomer", "TR", parent=CUSTOMER),
        obj(FN, "dbo", "ufnLeadingZeros", "FN"),
        obj(UNUSED_FN, "dbo", "ufnUnused", "FN"),  # not in closure -> never written
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
        col(
            CUSTOMER,
            4,
            "ModifiedDate",
            "datetime",
            default_name="DF_Customer_ModifiedDate",
            default_definition="(getdate())",
        ),
        col(VIEW, 1, "CustomerID"),
        col(VIEW, 2, "FirstName", "nvarchar", max_length=100),
        col(PERSON, 1, "BusinessEntityID"),
        col(PERSON, 2, "FirstName", "nvarchar", max_length=100),
        col(PERSON, 3, "LastName", "nvarchar", max_length=100),
        col(PERSON, 4, "AddressID", is_nullable=True),
        col(ADDRESS, 1, "AddressID"),
        col(ADDRESS, 2, "City", "nvarchar", max_length=60),
        col(UNUSED_FN, 1, "x"),
    ]
    r.parameters = [
        param(PROC, 1, "@CustomerID"),
        param(PROC, 2, "@Name", "nvarchar", max_length=200),
        param(FN, 0, "", "varchar", max_length=8),
        param(FN, 1, "@Value"),
    ]
    r.indexes = [
        idx(CUSTOMER, 1, "PK_Customer_CustomerID", 1, "CLUSTERED", True, True),
        idx(CUSTOMER, 2, "IX_Customer_PersonID", 2, "NONCLUSTERED", False, False),
        idx(PERSON, 1, "PK_Person_BusinessEntityID", 1, "CLUSTERED", True, True),
        idx(ADDRESS, 1, "PK_Address_AddressID", 1, "CLUSTERED", True, True),
    ]
    r.index_columns = [
        ic(CUSTOMER, 1, 1, 1, "CustomerID", 1),
        ic(CUSTOMER, 2, 1, 2, "PersonID", 1),
        ic(CUSTOMER, 2, 2, 3, "AccountNumber", 0, included=True),
        ic(PERSON, 1, 1, 1, "BusinessEntityID", 1),
        ic(ADDRESS, 1, 1, 1, "AddressID", 1),
    ]
    r.foreign_keys = [
        fk(900, "FK_Customer_Person_PersonID", CUSTOMER, PERSON),
        fk(901, "FK_Person_Address_AddressID", PERSON, ADDRESS),
    ]
    r.foreign_key_columns = [
        fkc(900, 1, CUSTOMER, 2, "PersonID", PERSON, 1, "BusinessEntityID"),
        fkc(901, 1, PERSON, 4, "AddressID", ADDRESS, 1, "AddressID"),
    ]
    r.check_constraints = [
        dict(
            object_id=902,
            name="CK_Customer_CustomerID",
            parent_object_id=CUSTOMER,
            parent_column_id=1,
            definition="([CustomerID]>(0))",
            is_disabled=False,
            is_not_trusted=False,
        )
    ]
    r.extended_properties = [
        ep(1, CUSTOMER, 0, "Customer master data."),
        ep(1, CUSTOMER, 1, "Primary key."),
        ep(1, PERSON, 0, "People."),
        ep(7, CUSTOMER, 2, "Lookup by person."),
        ep(2, FN, 0, "Zero-padded value."),
    ]
    r.modules = [
        mod(
            VIEW,
            "CREATE VIEW Sales.vCustomer AS SELECT c.CustomerID, p.FirstName "
            "FROM Sales.Customer c JOIN Person.Person p ON p.BusinessEntityID = c.PersonID",
        ),
        mod(
            PROC,
            "CREATE PROCEDURE Sales.uspUpdateCustomer @CustomerID int, @Name nvarchar(200) AS\n"
            "UPDATE c SET AccountNumber = UPPER(p.FirstName) FROM Sales.Customer c "
            "JOIN Person.Person p ON p.BusinessEntityID = c.PersonID\n"
            "EXEC(@sql)",
        ),
        mod(
            TRIG,
            "CREATE TRIGGER Sales.trCustomer ON Sales.Customer AFTER UPDATE AS "
            "EXEC Sales.uspUpdateCustomer 1, 'x'",
        ),
        mod(
            FN,
            "CREATE FUNCTION dbo.ufnLeadingZeros(@Value int) RETURNS varchar(8) AS "
            "BEGIN RETURN RIGHT('00000000' + CAST(@Value AS varchar(8)), 8) END",
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
            events="UPDATE",
        )
    ]
    return r


def closure() -> Closure:
    return Closure(
        scope={
            (DB, CUSTOMER): "in_scope",
            (DB, VIEW): "in_scope",
            (DB, PROC): "in_scope",
            (DB, TRIG): "in_scope",
            (DB, PERSON): "cascaded",
            (DB, ADDRESS): "cascaded",
            (DB, FN): "cascaded",
        },
        edges=[
            Edge(source=(DB, VIEW), target=(DB, CUSTOMER), kind="catalog"),
            Edge(source=(DB, VIEW), target=(DB, PERSON), kind="catalog"),
            Edge(source=(DB, CUSTOMER), target=(DB, PERSON), kind="fk", fk_id=900),
            Edge(source=(DB, PERSON), target=(DB, ADDRESS), kind="fk", fk_id=901),
            Edge(source=(DB, TRIG), target=(DB, CUSTOMER), kind="trigger"),
            Edge(source=(DB, PROC), target=(DB, CUSTOMER), kind="catalog"),
            Edge(source=(DB, PROC), target=(DB, PERSON), kind="catalog"),
            Edge(
                source=(DB, PROC),
                target=(DB, FN),
                kind="catalog",
                resolution="caller_dependent",
                is_caller_dependent=True,
                referenced_name="ufnLeadingZeros",
            ),
            Edge(
                source=(DB, PROC),
                target=None,
                kind="catalog",
                resolution="external",
                external_key=REMOTE.key,
                referenced_name="Remote",
            ),
            Edge(
                source=(DB, PROC),
                target=None,
                kind="catalog",
                resolution="ambiguous",
                referenced_name="value",
                is_ambiguous=True,
            ),
            Edge(
                source=(DB, CUSTOMER),
                target=(DB, FN),
                kind="catalog",
                referencing_minor_id=3,
                referenced_name="ufnLeadingZeros",
            ),
        ],
        externals={REMOTE.key: REMOTE},
    )


# -- seed ------------------------------------------------------------------------------


@dataclass
class Seed:
    scan_id: int
    failed_scan_id: int
    ids: dict[str, int] = field(default_factory=dict)
    cols: dict[tuple[str, str], int] = field(default_factory=dict)
    idx: dict[str, int] = field(default_factory=dict)


def seed_snapshot(db: Database) -> Seed:
    now = utcnow()
    with db.session() as s:
        failed = m.Scan(
            connection_name=CONN,
            status="failed",
            started_at=now - timedelta(days=2),
            finished_at=now - timedelta(days=2) + timedelta(seconds=1),
            error="pymssql.OperationalError: Login failed for user 'sa'",
        )
        s.add(failed)
        scan = m.Scan(
            connection_name=CONN,
            status="running",
            phase="extract",
            started_at=now - timedelta(seconds=10),
            server_name="SQLBOX",
            server_version="16.0.4000.1",
            server_edition="Developer Edition (64-bit)",
            server_start_time=now - timedelta(days=5),
            auth_scheme="SQL",
            driver="pymssql",
            options_json=json.dumps(ScanOptions().model_dump()),
        )
        s.add(scan)
        s.flush()
        raw = raw_database()
        clo = closure()
        w = SnapshotWriter(s, scan_id=scan.id, connection_name=CONN)
        w.write_database(
            raw,
            DatabaseCfg(name=DB, schemas=["Sales"]),
            permissions={"view_definition": True, "view_database_state": True},
        )
        w.write_objects(raw, clo)
        w.write_externals(clo)
        w.write_details(raw)
        w.write_dependencies(clo)
        s.flush()

        ids = {
            "customer": w.object_id(DB, CUSTOMER),
            "view": w.object_id(DB, VIEW),
            "person": w.object_id(DB, PERSON),
            "address": w.object_id(DB, ADDRESS),
            "proc": w.object_id(DB, PROC),
            "trig": w.object_id(DB, TRIG),
            "fn": w.object_id(DB, FN),
            "remote": w.external_id(REMOTE.key),
        }
        cols = {
            ("customer", "CustomerID"): w.column_id(DB, CUSTOMER, 1),
            ("customer", "PersonID"): w.column_id(DB, CUSTOMER, 2),
            ("customer", "AccountNumber"): w.column_id(DB, CUSTOMER, 3),
            ("customer", "ModifiedDate"): w.column_id(DB, CUSTOMER, 4),
            ("view", "CustomerID"): w.column_id(DB, VIEW, 1),
            ("view", "FirstName"): w.column_id(DB, VIEW, 2),
            ("person", "BusinessEntityID"): w.column_id(DB, PERSON, 1),
            ("person", "FirstName"): w.column_id(DB, PERSON, 2),
            ("person", "LastName"): w.column_id(DB, PERSON, 3),
            ("person", "AddressID"): w.column_id(DB, PERSON, 4),
            ("address", "AddressID"): w.column_id(DB, ADDRESS, 1),
            ("address", "City"): w.column_id(DB, ADDRESS, 2),
        }
        sid = scan.id

        # parsed object edges (proc reads Person, writes Customer; trigger executes proc)
        s.add_all(
            [
                m.ObjectDependency(
                    scan_id=sid,
                    source_object_id=ids["proc"],
                    target_object_id=ids["person"],
                    edge_kind="parsed_read",
                ),
                m.ObjectDependency(
                    scan_id=sid,
                    source_object_id=ids["proc"],
                    target_object_id=ids["customer"],
                    edge_kind="parsed_write",
                ),
                m.ObjectDependency(
                    scan_id=sid,
                    source_object_id=ids["trig"],
                    target_object_id=ids["proc"],
                    edge_kind="parsed_exec",
                ),
            ]
        )

        def lineage(src, tgt, confidence, transform, via=None, **kw):
            return m.ColumnLineage(
                scan_id=sid,
                source_object_id=None if src is None else _owner(cols, src),
                source_column_id=None if src is None else cols[src],
                source_column_name=kw.pop("source_column_name", None if src is None else src[1]),
                target_object_id=_owner(cols, tgt),
                target_column_id=cols[tgt],
                via_object_id=via,
                confidence=confidence,
                transform=transform,
                **kw,
            )

        def _owner(cols, key):
            return ids[key[0]]

        s.add_all(
            [
                lineage(
                    ("person", "FirstName"),
                    ("view", "FirstName"),
                    "exact",
                    "passthrough",
                    statement_index=0,
                    statement_kind="select",
                    expression_sql="p.FirstName",
                ),
                lineage(
                    ("customer", "CustomerID"),
                    ("view", "CustomerID"),
                    "exact",
                    "passthrough",
                    statement_index=0,
                    statement_kind="select",
                ),
                lineage(
                    ("person", "FirstName"),
                    ("customer", "AccountNumber"),
                    "inferred",
                    "expression",
                    via=ids["proc"],
                    statement_index=1,
                    statement_kind="update",
                    expression_sql="UPPER(p.FirstName)",
                ),
                lineage(
                    ("customer", "CustomerID"),
                    ("customer", "AccountNumber"),
                    "inferred",
                    "computed",
                    expression_sql="isnull('AW'+[dbo].[ufnLeadingZeros]([CustomerID]),'')",
                ),
                lineage(
                    None,
                    ("customer", "PersonID"),
                    "unresolved",
                    "temp",
                    via=ids["proc"],
                    source_column_name="#tmp.PersonID",
                    statement_index=1,
                    statement_kind="update",
                ),
            ]
        )
        s.add_all(
            [
                m.LineageIssue(
                    scan_id=sid,
                    object_id=ids["proc"],
                    statement_index=2,
                    kind="dynamic_sql",
                    message="EXEC(@sql): dynamic SQL is not analyzed",
                    snippet="EXEC(@sql)",
                ),
                m.LineageIssue(
                    scan_id=sid,
                    object_id=ids["trig"],
                    statement_index=0,
                    kind="parse_error",
                    message="unexpected token",
                    snippet=None,
                ),
            ]
        )
        for key, status in (("view", "ok"), ("proc", "partial"), ("trig", "failed"), ("fn", "ok")):
            s.get(m.DbObject, ids[key]).lineage_status = status
        s.get(m.DbObject, ids["proc"]).has_dynamic_sql = True

        # stats
        s.add_all(
            [
                m.TableStats(
                    scan_id=sid,
                    object_id=ids["customer"],
                    row_count=19820,
                    data_kb=1024,
                    index_kb=512,
                    reserved_kb=1600,
                    partition_count=1,
                    is_heap=False,
                    compression="NONE",
                ),
                m.TableStats(
                    scan_id=sid,
                    object_id=ids["person"],
                    row_count=19972,
                    data_kb=4096,
                    index_kb=2048,
                    reserved_kb=6200,
                    partition_count=1,
                    is_heap=False,
                    compression="PAGE",
                ),
                m.TableStats(
                    scan_id=sid,
                    object_id=ids["address"],
                    row_count=19614,
                    data_kb=512,
                    index_kb=128,
                    reserved_kb=700,
                    partition_count=1,
                    is_heap=True,
                    compression="NONE",
                ),
            ]
        )
        index_rows = {
            (r.object_id, r.name): r.id for r in s.execute(select_indexes(sid)).scalars().all()
        }
        idx_ids = {
            "pk_customer": index_rows[(ids["customer"], "PK_Customer_CustomerID")],
            "ix_customer_person": index_rows[(ids["customer"], "IX_Customer_PersonID")],
            "pk_person": index_rows[(ids["person"], "PK_Person_BusinessEntityID")],
            "pk_address": index_rows[(ids["address"], "PK_Address_AddressID")],
        }
        s.add_all(
            [
                m.IndexUsage(
                    scan_id=sid,
                    index_id=idx_ids["pk_customer"],
                    user_seeks=100,
                    user_scans=5,
                    user_lookups=0,
                    user_updates=20,
                    last_user_seek=now - timedelta(hours=1),
                    is_unused=False,
                ),
                m.IndexUsage(
                    scan_id=sid,
                    index_id=idx_ids["ix_customer_person"],
                    user_seeks=0,
                    user_scans=0,
                    user_lookups=0,
                    user_updates=20,
                    last_user_update=now - timedelta(hours=2),
                    is_unused=True,
                ),
                m.IndexUsage(
                    scan_id=sid,
                    index_id=idx_ids["pk_person"],
                    user_seeks=50,
                    user_scans=1,
                    user_lookups=2,
                    user_updates=3,
                    is_unused=False,
                ),
                m.IndexUsage(
                    scan_id=sid,
                    index_id=idx_ids["pk_address"],
                    user_seeks=1,
                    is_unused=False,
                ),
                m.ProcStats(
                    scan_id=sid,
                    object_id=ids["proc"],
                    execution_count=42,
                    total_elapsed_us=4_200_000,
                    avg_elapsed_us=100_000,
                    min_elapsed_us=50_000,
                    max_elapsed_us=300_000,
                    total_cpu_us=2_000_000,
                    total_logical_reads=1234,
                    last_execution_time=now - timedelta(hours=1),
                    cached_time=now - timedelta(days=2),
                ),
                m.ProcStats(
                    scan_id=sid,
                    object_id=ids["fn"],
                    execution_count=7,
                    total_elapsed_us=7_000,
                    avg_elapsed_us=1_000,
                    min_elapsed_us=500,
                    max_elapsed_us=2_000,
                    total_cpu_us=3_500,
                    total_logical_reads=0,
                ),
                m.MissingIndex(
                    scan_id=sid,
                    object_id=ids["customer"],
                    index_handle=1,
                    equality_columns="[PersonID]",
                    inequality_columns=None,
                    included_columns="[AccountNumber]",
                    unique_compiles=3,
                    user_seeks=5,
                    user_scans=0,
                    avg_total_user_cost=10.5,
                    avg_user_impact=80.0,
                    improvement_measure=4200.0,
                    suggested_ddl="CREATE NONCLUSTERED INDEX [IX_Customer_PersonID_missing] "
                    "ON [Sales].[Customer] ([PersonID]) INCLUDE ([AccountNumber])",
                ),
                m.MissingIndex(
                    scan_id=sid,
                    object_id=ids["person"],
                    index_handle=2,
                    equality_columns="[LastName]",
                    inequality_columns=None,
                    included_columns=None,
                    unique_compiles=10,
                    user_seeks=50,
                    user_scans=0,
                    avg_total_user_cost=20.0,
                    avg_user_impact=90.0,
                    improvement_measure=90000.0,
                    suggested_ddl="CREATE NONCLUSTERED INDEX [IX_Person_LastName_missing] "
                    "ON [Person].[Person] ([LastName])",
                ),
                m.ScanWarning(
                    scan_id=sid,
                    phase="stats",
                    database_name=DB,
                    code="stats_unavailable",
                    message="dm_db_missing_index_group_stats: permission denied",
                ),
            ]
        )
        s.flush()

        # annotations & tags (not scan scoped)
        s.add_all(
            [
                m.Annotation(
                    target_kind="object",
                    target_key=f"{CONN}|{DB}|Sales|Customer",
                    description="Customer master (user)",
                    notes="Owned by the CRM team",
                ),
                m.Annotation(
                    target_kind="column",
                    target_key=f"{CONN}|{DB}|Sales|Customer|CustomerID",
                    description="Surrogate key",
                ),
            ]
        )
        core = m.Tag(name="core", color="#3b82f6")
        pii = m.Tag(name="pii", color="#ef4444")
        s.add_all([core, pii])
        s.flush()
        s.add_all(
            [
                m.TagAssignment(
                    tag_id=core.id, target_kind="object", target_key=f"{CONN}|{DB}|Sales|Customer"
                ),
                m.TagAssignment(
                    tag_id=pii.id, target_kind="object", target_key=f"{CONN}|{DB}|Person|Person"
                ),
                m.TagAssignment(
                    tag_id=pii.id,
                    target_kind="column",
                    target_key=f"{CONN}|{DB}|Person|Person|FirstName",
                ),
            ]
        )

        # finalize the scan
        scan.summary_json = json.dumps(scan_counts(s, sid))
        scan.status = "succeeded"
        scan.phase = "finalize"
        scan.finished_at = now
        s.commit()
        return Seed(scan_id=sid, failed_scan_id=failed.id, ids=ids, cols=cols, idx=idx_ids)


def select_indexes(scan_id):
    from sqlalchemy import select

    return select(m.IndexDef).where(m.IndexDef.scan_id == scan_id)


# -- runtime ---------------------------------------------------------------------------


class StubRunner:
    """Scan runner that completes immediately unless ``gate`` is cleared."""

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.gate.set()
        self.calls: list[tuple[str, Any]] = []

    def __call__(self, db, cfg, conn_cfg, scan_id, progress, options) -> None:
        self.calls.append((conn_cfg.name, options))
        progress.start_phase("connect", total=1, message="stub")
        while not self.gate.wait(0.02):
            if progress.cancelled:
                with db.session() as s:
                    scan = s.get(m.Scan, scan_id)
                    scan.status = "cancelled"
                    scan.finished_at = utcnow()
                    s.commit()
                progress.finish("cancelled")
                return
        with db.session() as s:
            scan = s.get(m.Scan, scan_id)
            scan.status = "succeeded"
            scan.finished_at = utcnow()
            scan.summary_json = json.dumps(scan_counts(s, scan_id))
            s.commit()
        progress.finish("succeeded")


@dataclass
class Seeded:
    runtime: Runtime
    runner: StubRunner
    seed: Seed
    tmp: Path


def build_runtime(tmp: Path) -> Seeded:
    db = Database.open(tmp / "api.sqlite")
    seed = seed_snapshot(db)
    cfg = AppConfig(
        storage=StorageCfg(sqlite_path=tmp / "api.sqlite"),
        connections=[
            ConnectionCfg(
                name=CONN,
                host="localhost",
                port=1433,
                auth=AuthCfg(mode="sql", username="sa", password="hunter2"),
                driver="pymssql",
                databases=[DatabaseCfg(name=DB, schemas=["Sales"])],
            ),
            ConnectionCfg(
                name="dw",
                host="sqlprod01",
                auth=AuthCfg(mode="integrated"),
                databases=[DatabaseCfg(name="DW", schemas=["dbo"])],
            ),
        ],
    )
    config_path = tmp / "sqldoc.yaml"
    config_path.write_text(CONFIG_YAML)
    runner = StubRunner()
    runtime = Runtime(
        cfg=cfg, db=db, manager=ScanManager(db, cfg, runner=runner), config_path=config_path
    )
    return Seeded(runtime=runtime, runner=runner, seed=seed, tmp=tmp)


@pytest.fixture(scope="module")
def seeded(tmp_path_factory) -> Seeded:
    return build_runtime(tmp_path_factory.mktemp("api"))


@pytest.fixture(scope="module")
def client(seeded) -> TestClient:
    with TestClient(create_app(seeded.runtime)) as c:
        yield c
