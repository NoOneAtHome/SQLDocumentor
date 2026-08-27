"""Column lineage for views: one query, edges terminate at the objects it selects from."""

import pytest

from sqldoc.lineage.engine import analyze_view
from sqldoc.lineage.schema_builder import LineageCatalog


@pytest.fixture
def catalog() -> LineageCatalog:
    cat = LineageCatalog(default_db="AW")
    cat.add_table("AW", "Sales", "Customer", ["CustomerID", "PersonID", "StoreID"])
    cat.add_table("AW", "Person", "Person", ["BusinessEntityID", "FirstName", "LastName", "Title"])
    cat.add_table("AW", "Sales", "vInner", ["Name"])
    cat.add_table("AW", "Sales", "Individual", ["CustomerID", "Demographics"])
    cat.add_table("AW", "dbo", "T", ["x"])
    cat.add_table("Staging", "etl", "Loads", ["Id"])
    return cat


def run(catalog, sql, outputs, database="AW"):
    definition = f"CREATE VIEW Sales.v AS {sql}" if not sql.upper().startswith("CREATE") else sql
    result = analyze_view(definition, database=database, output_columns=outputs, catalog=catalog)
    edges = {
        (
            e.target_column,
            (e.source_table.schema, e.source_table.name) if e.source_table else e.source_name,
            e.source_column,
            e.confidence,
            e.transform,
        )
        for e in result.column_edges
    }
    return result, edges


def test_passthrough_join(catalog):
    result, edges = run(
        catalog,
        "SELECT c.CustomerID, p.FirstName AS GivenName FROM Sales.Customer c "
        "JOIN Person.Person p ON p.BusinessEntityID = c.PersonID",
        ["CustomerID", "GivenName"],
    )
    assert edges == {
        ("CustomerID", ("Sales", "Customer"), "CustomerID", "exact", "passthrough"),
        ("GivenName", ("Person", "Person"), "FirstName", "exact", "passthrough"),
    }
    assert result.status == "ok" and result.issues == []
    reads = {(r.table.schema, r.table.name) for r in result.object_refs if r.kind == "read"}
    assert reads == {("Sales", "Customer"), ("Person", "Person")}


def test_expressions_are_inferred(catalog):
    _, edges = run(
        catalog,
        "SELECT ISNULL(p.Title, '') AS T, p.FirstName + ' ' + p.LastName AS FullName "
        "FROM Person.Person p",
        ["T", "FullName"],
    )
    assert edges == {
        ("T", ("Person", "Person"), "Title", "inferred", "expression"),
        ("FullName", ("Person", "Person"), "FirstName", "inferred", "expression"),
        ("FullName", ("Person", "Person"), "LastName", "inferred", "expression"),
    }


def test_aggregates(catalog):
    _, edges = run(
        catalog,
        "SELECT c.StoreID, COUNT(*) AS N, MAX(c.PersonID) AS MaxP FROM Sales.Customer c "
        "GROUP BY c.StoreID",
        ["StoreID", "N", "MaxP"],
    )
    assert edges == {
        ("StoreID", ("Sales", "Customer"), "StoreID", "exact", "passthrough"),
        ("MaxP", ("Sales", "Customer"), "PersonID", "inferred", "aggregate"),
    }


def test_cte_and_derived_table_stay_exact(catalog):
    _, cte = run(
        catalog, "WITH x AS (SELECT CustomerID AS id FROM Sales.Customer) SELECT id FROM x", ["id"]
    )
    _, derived = run(
        catalog, "SELECT d.id FROM (SELECT CustomerID AS id FROM Sales.Customer) d", ["id"]
    )
    expected = {("id", ("Sales", "Customer"), "CustomerID", "exact", "passthrough")}
    assert cte == expected and derived == expected


def test_cte_with_expression_is_inferred(catalog):
    _, edges = run(
        catalog,
        "WITH x AS (SELECT CustomerID * 2 AS id FROM Sales.Customer) SELECT id FROM x",
        ["id"],
    )
    assert edges == {("id", ("Sales", "Customer"), "CustomerID", "inferred", "expression")}


def test_union_all_merges_sources(catalog):
    _, edges = run(
        catalog,
        "SELECT CustomerID FROM Sales.Customer "
        "UNION ALL SELECT BusinessEntityID FROM Person.Person",
        ["CustomerID"],
    )
    assert edges == {
        ("CustomerID", ("Sales", "Customer"), "CustomerID", "exact", "passthrough"),
        ("CustomerID", ("Person", "Person"), "BusinessEntityID", "exact", "passthrough"),
    }


def test_select_star_expands_with_known_schema(catalog):
    _, edges = run(catalog, "SELECT * FROM Sales.Customer", ["CustomerID", "PersonID", "StoreID"])
    assert edges == {
        ("CustomerID", ("Sales", "Customer"), "CustomerID", "exact", "passthrough"),
        ("PersonID", ("Sales", "Customer"), "PersonID", "exact", "passthrough"),
        ("StoreID", ("Sales", "Customer"), "StoreID", "exact", "passthrough"),
    }


def test_select_star_from_unknown_table_is_unresolved(catalog):
    result, edges = run(catalog, "SELECT * FROM Sales.Unknown", ["A"])
    assert edges == {("A", "Sales.Unknown", "*", "unresolved", "star")}
    unresolved_reads = [r for r in result.object_refs if r.kind == "read" and r.table is None]
    assert unresolved_reads and unresolved_reads[0].display() == "Sales.Unknown"


def test_three_part_and_default_schema_names(catalog):
    _, three = run(catalog, "SELECT l.Id FROM Staging.etl.Loads l", ["Id"])
    _, default = run(catalog, "SELECT x FROM T", ["x"])
    assert three == {("Id", ("etl", "Loads"), "Id", "exact", "passthrough")}
    assert default == {("x", ("dbo", "T"), "x", "exact", "passthrough")}


def test_scalar_udf_call_records_function_ref(catalog):
    result, edges = run(
        catalog, "SELECT dbo.ufnLeadingZeros(c.CustomerID) AS Z FROM Sales.Customer c", ["Z"]
    )
    assert edges == {("Z", ("Sales", "Customer"), "CustomerID", "inferred", "expression")}
    funcs = [(r.schema, r.name) for r in result.object_refs if r.kind == "function"]
    assert funcs == [("dbo", "ufnLeadingZeros")]


def test_xml_method_call_falls_back_to_column_scan(catalog):
    _, edges = run(
        catalog, "SELECT i.Demographics.value('(/x)[1]', 'int') AS X FROM Sales.Individual i", ["X"]
    )
    assert edges == {("X", ("Sales", "Individual"), "Demographics", "inferred", "expression")}


def test_view_over_view_stops_at_inner_view(catalog):
    _, edges = run(catalog, "SELECT v2.Name FROM Sales.vInner v2", ["Name"])
    assert edges == {("Name", ("Sales", "vInner"), "Name", "exact", "passthrough")}


def test_unknown_column_on_known_table_is_inferred(catalog):
    _, edges = run(catalog, "SELECT c.Ghost FROM Sales.Customer c", ["Ghost"])
    assert edges == {("Ghost", ("Sales", "Customer"), "Ghost", "inferred", "passthrough")}


def test_output_columns_map_by_position(catalog):
    _, edges = run(
        catalog,
        "CREATE VIEW Sales.v (A, B) AS SELECT CustomerID, PersonID FROM Sales.Customer",
        ["A", "B"],
    )
    assert {e[0] for e in edges} == {"A", "B"}


def test_column_count_mismatch_falls_back_to_names(catalog):
    result, edges = run(
        catalog,
        "SELECT CustomerID, PersonID, StoreID FROM Sales.Customer",
        ["PersonID", "CustomerID"],
    )
    assert {e[0] for e in edges} == {"PersonID", "CustomerID"}
    assert [i.kind for i in result.issues] == ["column_count_mismatch"]
    assert result.status == "partial"


def test_parse_failure_is_reported(catalog):
    result, edges = run(catalog, "SELECT FROM WHERE (", ["A"])
    assert edges == set()
    assert result.status == "failed"
    assert result.issues[0].kind == "parse_error" and result.issues[0].snippet


def test_edges_carry_expression_and_statement_metadata(catalog):
    result, _ = run(catalog, "SELECT UPPER(c.CustomerID) AS U FROM Sales.Customer c", ["U"])
    edge = result.column_edges[0]
    assert "UPPER" in edge.expression_sql.upper()
    assert edge.statement_index == 0 and edge.statement_kind == "view"
