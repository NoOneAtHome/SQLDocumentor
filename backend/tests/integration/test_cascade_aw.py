"""Cascade closure on the live AdventureWorks2022 database."""

import pytest

from sqldoc.config.schema import AuthCfg, ConnectionCfg, DatabaseCfg, ScanOptions
from sqldoc.mssql.catalog import CatalogExtractor
from sqldoc.scope.adapt import (
    dependencies_from_raw,
    foreign_keys_from_raw,
    synonyms_from_raw,
    triggers_from_raw,
    universe_from_raw,
)
from sqldoc.scope.cascade import compute_closure

pytestmark = pytest.mark.integration
DB = "AdventureWorks2022"


@pytest.fixture(scope="module")
def raw_rows(aw_client):
    ex = CatalogExtractor(aw_client)
    return {
        "objects": ex.objects(),
        "deps": ex.dependencies(),
        "fks": ex.foreign_keys(),
        "triggers": ex.triggers(),
        "synonyms": ex.synonyms(),
        "server": ex.server_info()["server_name"],
    }


def closure_for(raw_rows, schemas, **opts):
    conn = ConnectionCfg(
        name="aw",
        host="localhost",
        auth=AuthCfg(mode="integrated"),
        databases=[DatabaseCfg(name=DB, schemas=schemas)],
    )
    universe = universe_from_raw({DB: raw_rows["objects"]})
    return universe, compute_closure(
        universe,
        dependencies_from_raw(DB, raw_rows["deps"]),
        foreign_keys_from_raw(DB, raw_rows["fks"]),
        triggers_from_raw(DB, raw_rows["triggers"]),
        synonyms_from_raw(DB, raw_rows["synonyms"]),
        conn,
        ScanOptions(**opts),
        server_name=raw_rows["server"],
    )


def names(universe, closure, status):
    return {
        f"{universe.by_id[oid].schema}.{universe.by_id[oid].name}"
        for oid, s in closure.scope.items()
        if s == status
    }


def test_sales_scope_cascades_expected_objects(raw_rows):
    universe, closure = closure_for(raw_rows, ["Sales"])
    in_scope = names(universe, closure, "in_scope")
    cascaded = names(universe, closure, "cascaded")
    assert "Sales.Customer" in in_scope and "Sales.vIndividualCustomer" in in_scope
    assert all(n.startswith("Sales.") for n in in_scope)
    assert {
        "Person.Person",
        "Person.Address",
        "Person.StateProvince",
        "Person.CountryRegion",
        "Person.EmailAddress",
        "Person.PersonPhone",
        "Person.BusinessEntityContact",
        "HumanResources.Employee",
        "Production.TransactionHistory",
        "dbo.uspLogError",
        "dbo.uspPrintError",
        "dbo.ufnGetAccountingStartDate",
        "dbo.ufnLeadingZeros",
        "Production.Product",
    } <= cascaded
    assert closure.externals == {}, "no external nodes: ambiguous method-call rows must not leak"
    assert any(e.resolution == "ambiguous" for e in closure.edges)


def test_disabling_fk_cascade_shrinks_the_closure(raw_rows):
    universe, full = closure_for(raw_rows, ["Sales"])
    _, no_fk = closure_for(raw_rows, ["Sales"], cascade_foreign_keys=False)
    assert len(no_fk.scope) < len(full.scope)
    assert "Production.Product" not in names(universe, no_fk, "cascaded")


def test_humanresources_scope_reaches_person_tables(raw_rows):
    universe, closure = closure_for(raw_rows, ["HumanResources"])
    cascaded = names(universe, closure, "cascaded")
    assert {"Person.Person", "Person.BusinessEntity"} <= cascaded
