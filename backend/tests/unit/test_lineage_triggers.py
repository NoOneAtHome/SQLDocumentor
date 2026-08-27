"""Trigger lineage: inserted/deleted map back to the parent table."""

import pytest

from sqldoc.lineage.engine import analyze_module
from sqldoc.lineage.schema_builder import LineageCatalog, TableKey


@pytest.fixture
def catalog() -> LineageCatalog:
    cat = LineageCatalog(default_db="AW")
    cat.add_table(
        "AW", "Sales", "SalesOrderDetail", ["SalesOrderID", "ProductID", "OrderQty", "LineTotal"]
    )
    cat.add_table("AW", "Sales", "SalesOrderHeader", ["SalesOrderID", "SubTotal"])
    cat.add_table(
        "AW", "Production", "TransactionHistory", ["ProductID", "Quantity", "ReferenceOrderID"]
    )
    return cat


def run(catalog, body):
    definition = (
        "CREATE TRIGGER Sales.iduSalesOrderDetail ON Sales.SalesOrderDetail AFTER "
        f"INSERT, UPDATE AS BEGIN {body} END"
    )
    result = analyze_module(
        definition,
        kind="trigger",
        database="AW",
        schema="Sales",
        name="iduSalesOrderDetail",
        catalog=catalog,
        parent_table=TableKey("AW", "Sales", "SalesOrderDetail"),
    )
    edges = {
        (
            e.target_table.display() if e.target_table else None,
            e.target_column,
            e.source_table.display() if e.source_table else e.source_name,
            e.source_column,
            e.confidence,
            e.transform,
            e.via,
        )
        for e in result.column_edges
    }
    return result, edges


def test_inserted_rows_map_to_parent_table_columns(catalog):
    result, edges = run(
        catalog,
        "INSERT INTO Production.TransactionHistory (ProductID, Quantity, ReferenceOrderID) "
        "SELECT inserted.ProductID, inserted.OrderQty, inserted.SalesOrderID FROM inserted",
    )
    assert edges == {
        (
            "Production.TransactionHistory",
            "ProductID",
            "Sales.SalesOrderDetail",
            "ProductID",
            "exact",
            "passthrough",
            "inserted",
        ),
        (
            "Production.TransactionHistory",
            "Quantity",
            "Sales.SalesOrderDetail",
            "OrderQty",
            "exact",
            "passthrough",
            "inserted",
        ),
        (
            "Production.TransactionHistory",
            "ReferenceOrderID",
            "Sales.SalesOrderDetail",
            "SalesOrderID",
            "exact",
            "passthrough",
            "inserted",
        ),
    }
    reads = {r.display() for r in result.object_refs if r.kind == "read"}
    assert "inserted" not in reads and "dbo.inserted" not in reads
    assert result.status == "ok"


def test_aggregate_update_from_detail_table(catalog):
    _, edges = run(
        catalog,
        "UPDATE Sales.SalesOrderHeader SET SubTotal = (SELECT SUM(d.LineTotal) "
        "FROM Sales.SalesOrderDetail d "
        "WHERE d.SalesOrderID = Sales.SalesOrderHeader.SalesOrderID) "
        "WHERE SalesOrderID IN (SELECT inserted.SalesOrderID FROM inserted)",
    )
    assert (
        "Sales.SalesOrderHeader",
        "SubTotal",
        "Sales.SalesOrderDetail",
        "LineTotal",
        "inferred",
        "aggregate",
        None,
    ) in edges


def test_deleted_rows_are_tagged_via_deleted(catalog):
    _, edges = run(
        catalog,
        "INSERT INTO Production.TransactionHistory (ProductID) SELECT d.ProductID FROM deleted d",
    )
    assert edges == {
        (
            "Production.TransactionHistory",
            "ProductID",
            "Sales.SalesOrderDetail",
            "ProductID",
            "exact",
            "passthrough",
            "deleted",
        ),
    }
