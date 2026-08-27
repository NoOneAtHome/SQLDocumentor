"""Column lineage for procedures and functions (DML rewrite, temp tables, result sets)."""

import pytest

from sqldoc.lineage.engine import analyze_module
from sqldoc.lineage.schema_builder import TABLEVAR_SCHEMA, TEMP_SCHEMA, LineageCatalog


@pytest.fixture
def catalog() -> LineageCatalog:
    cat = LineageCatalog(default_db="AW")
    cat.add_table("AW", "Sales", "Customer", ["CustomerID", "PersonID", "StoreID"])
    cat.add_table("AW", "Person", "Person", ["BusinessEntityID", "FirstName", "LastName"])
    cat.add_table("AW", "Sales", "Archive", ["Id", "Name", "Note"])
    cat.add_table("AW", "Sales", "Totals", ["CustomerID", "Total"])
    return cat


def proc(body: str) -> str:
    return f"CREATE PROCEDURE Sales.uspX @s int = 1 AS BEGIN SET NOCOUNT ON {body} END"


def run(catalog, definition, kind="procedure", **kw):
    result = analyze_module(
        definition, kind=kind, database="AW", schema="Sales", name="uspX", catalog=catalog, **kw
    )
    edges = {
        (
            e.target_kind,
            e.target_table.display() if e.target_table else None,
            e.target_column,
            e.source_table.display() if e.source_table else e.source_name,
            e.source_column,
            e.confidence,
            e.transform,
        )
        for e in result.column_edges
    }
    return result, edges


def refs(result, kind):
    return {r.display() for r in result.object_refs if r.kind == kind}


def test_insert_select_with_column_list(catalog):
    result, edges = run(
        catalog,
        proc(
            "INSERT INTO Sales.Archive (Id, Name) SELECT c.CustomerID, p.FirstName "
            "FROM Sales.Customer c JOIN Person.Person p ON p.BusinessEntityID = c.PersonID"
        ),
    )
    assert edges == {
        ("table", "Sales.Archive", "Id", "Sales.Customer", "CustomerID", "exact", "passthrough"),
        ("table", "Sales.Archive", "Name", "Person.Person", "FirstName", "exact", "passthrough"),
    }
    assert refs(result, "write") == {"Sales.Archive"}
    assert refs(result, "read") == {"Sales.Customer", "Person.Person"}
    assert result.status == "ok"


def test_insert_positional_uses_catalog_column_order(catalog):
    _, edges = run(
        catalog,
        proc("INSERT INTO Sales.Archive SELECT CustomerID, PersonID, StoreID FROM Sales.Customer"),
    )
    assert {(e[2], e[4]) for e in edges} == {
        ("Id", "CustomerID"),
        ("Name", "PersonID"),
        ("Note", "StoreID"),
    }


def test_update_from_with_alias_target(catalog):
    _, edges = run(
        catalog,
        proc(
            "UPDATE c SET c.PersonID = p.BusinessEntityID, StoreID = 5 "
            "FROM Sales.Customer c JOIN Person.Person p ON p.FirstName = 'x' WHERE c.CustomerID > 1"
        ),
    )
    assert edges == {
        (
            "table",
            "Sales.Customer",
            "PersonID",
            "Person.Person",
            "BusinessEntityID",
            "exact",
            "passthrough",
        ),
    }


def test_update_without_from_is_self_referential(catalog):
    _, edges = run(
        catalog, proc("UPDATE Sales.Customer SET PersonID = StoreID + 1 WHERE CustomerID = @s")
    )
    assert edges == {
        (
            "table",
            "Sales.Customer",
            "PersonID",
            "Sales.Customer",
            "StoreID",
            "inferred",
            "expression",
        ),
    }


def test_merge_update_and_insert_branches(catalog):
    _, edges = run(
        catalog,
        proc(
            "MERGE INTO Sales.Totals AS tgt USING Sales.Customer AS src ON "
            "tgt.CustomerID = src.CustomerID "
            "WHEN MATCHED THEN UPDATE SET Total = src.StoreID "
            "WHEN NOT MATCHED THEN INSERT (CustomerID, Total) VALUES (src.CustomerID, src.StoreID);"
        ),
    )
    assert edges == {
        ("table", "Sales.Totals", "Total", "Sales.Customer", "StoreID", "exact", "passthrough"),
        (
            "table",
            "Sales.Totals",
            "CustomerID",
            "Sales.Customer",
            "CustomerID",
            "exact",
            "passthrough",
        ),
    }


def test_temp_table_chain(catalog):
    result, edges = run(
        catalog,
        proc(
            "SELECT c.CustomerID AS Id, c.StoreID AS S INTO #tmp FROM Sales.Customer c "
            "INSERT INTO Sales.Archive (Id, Note) SELECT t.Id, t.S FROM #tmp t"
        ),
    )
    assert (
        "temp",
        f"{TEMP_SCHEMA}.tmp",
        "Id",
        "Sales.Customer",
        "CustomerID",
        "exact",
        "passthrough",
    ) in edges
    assert ("table", "Sales.Archive", "Id", f"{TEMP_SCHEMA}.tmp", "Id", "exact", "temp") in edges
    assert ("table", "Sales.Archive", "Note", f"{TEMP_SCHEMA}.tmp", "S", "exact", "temp") in edges
    assert result.status == "ok"


def test_table_variable_and_result_sets(catalog):
    result, edges = run(
        catalog,
        proc(
            "DECLARE @tv TABLE (Id int, Nm nvarchar(50)) "
            "INSERT INTO @tv (Id) SELECT CustomerID FROM Sales.Customer "
            "SELECT v.Id, v.Nm FROM @tv v "
            "SELECT p.FirstName AS Given FROM Person.Person p"
        ),
    )
    assert (
        "tablevar",
        f"{TABLEVAR_SCHEMA}.tv",
        "Id",
        "Sales.Customer",
        "CustomerID",
        "exact",
        "passthrough",
    ) in edges
    assert ("resultset", None, "Id", f"{TABLEVAR_SCHEMA}.tv", "Id", "exact", "temp") in edges
    assert (
        "resultset",
        None,
        "Given",
        "Person.Person",
        "FirstName",
        "exact",
        "passthrough",
    ) in edges
    assert result.resultsets == [["Id", "Nm"], ["Given"]]
    by_target = {
        e.target_column: e.resultset_index
        for e in result.column_edges
        if e.target_kind == "resultset"
    }
    assert by_target == {"Id": 0, "Nm": 0, "Given": 1}


def test_insert_exec_is_unresolved_but_recorded(catalog):
    result, edges = run(catalog, proc("INSERT INTO Sales.Archive (Id, Name) EXEC dbo.uspSource @s"))
    assert refs(result, "write") == {"Sales.Archive"}
    assert refs(result, "exec") == {"dbo.uspSource"}
    assert edges == {
        ("table", "Sales.Archive", "Id", "dbo.uspSource", "*", "unresolved", "pseudo"),
        ("table", "Sales.Archive", "Name", "dbo.uspSource", "*", "unresolved", "pseudo"),
    }


def test_exec_and_dynamic_sql(catalog):
    result, _ = run(
        catalog, proc("EXEC dbo.uspLogError @s OUTPUT EXEC (@sql) EXEC sp_executesql @sql")
    )
    assert refs(result, "exec") == {"dbo.uspLogError"}
    assert result.has_dynamic_sql
    assert [i.kind for i in result.issues] == ["dynamic_sql", "dynamic_sql"]
    assert result.status == "partial"


def test_statement_isolation(catalog):
    result, edges = run(
        catalog,
        proc(
            "SELECT FROM WHERE INSERT INTO Sales.Archive (Id) SELECT CustomerID FROM Sales.Customer"
        ),
    )
    assert (
        "table",
        "Sales.Archive",
        "Id",
        "Sales.Customer",
        "CustomerID",
        "exact",
        "passthrough",
    ) in edges
    parse_issues = [i for i in result.issues if i.kind == "parse_error"]
    assert len(parse_issues) == 1 and parse_issues[0].statement_index is not None
    assert result.status == "partial"


def test_variable_assignment_reads_only(catalog):
    result, edges = run(
        catalog, proc("SELECT @s = c.StoreID FROM Sales.Customer c WHERE c.CustomerID = 1")
    )
    assert edges == set()
    assert refs(result, "read") == {"Sales.Customer"}
    assert result.resultsets == []


def test_delete_is_a_write_reference(catalog):
    result, edges = run(
        catalog,
        proc(
            "DELETE FROM Sales.Archive WHERE Id = @s DELETE a FROM Sales.Archive a JOIN "
            "Sales.Customer c ON c.CustomerID = a.Id"
        ),
    )
    assert edges == set()
    assert refs(result, "write") == {"Sales.Archive"}
    assert refs(result, "read") >= {"Sales.Customer"}


def test_output_into_clause_is_stripped_with_issue(catalog):
    result, edges = run(
        catalog,
        proc(
            "INSERT INTO Sales.Archive (Id) OUTPUT inserted.Id INTO @log (Id) "
            "SELECT CustomerID FROM Sales.Customer"
        ),
    )
    assert (
        "table",
        "Sales.Archive",
        "Id",
        "Sales.Customer",
        "CustomerID",
        "exact",
        "passthrough",
    ) in edges
    assert [i.kind for i in result.issues] == ["unsupported"]


def test_select_into_real_table(catalog):
    _, edges = run(
        catalog,
        proc("SELECT CustomerID AS Id, StoreID AS Note INTO Sales.Archive FROM Sales.Customer"),
    )
    assert (
        "table",
        "Sales.Archive",
        "Id",
        "Sales.Customer",
        "CustomerID",
        "exact",
        "passthrough",
    ) in edges


def test_inline_tvf(catalog):
    definition = (
        "CREATE FUNCTION Sales.fnX (@s int) RETURNS TABLE AS RETURN "
        "(SELECT c.CustomerID AS Id, c.StoreID AS S FROM Sales.Customer c WHERE c.StoreID = @s)"
    )
    result, edges = run(catalog, definition, kind="inline_tvf", output_columns=["Id", "S"])
    assert edges == {
        ("self", None, "Id", "Sales.Customer", "CustomerID", "exact", "passthrough"),
        ("self", None, "S", "Sales.Customer", "StoreID", "exact", "passthrough"),
    }


def test_multi_statement_tvf_retargets_return_variable(catalog):
    definition = (
        "CREATE FUNCTION Sales.fnX (@s int) RETURNS @ret TABLE (Id int, Nm nvarchar(50)) AS BEGIN "
        "INSERT @ret (Id, Nm) SELECT c.CustomerID, p.FirstName FROM Sales.Customer c "
        "JOIN Person.Person p ON p.BusinessEntityID = c.PersonID RETURN END"
    )
    _, edges = run(catalog, definition, kind="table_function", output_columns=["Id", "Nm"])
    assert edges == {
        ("self", None, "Id", "Sales.Customer", "CustomerID", "exact", "passthrough"),
        ("self", None, "Nm", "Person.Person", "FirstName", "exact", "passthrough"),
    }


def test_scalar_function_return_value(catalog):
    definition = (
        "CREATE FUNCTION Sales.fnMax (@s int) RETURNS int AS BEGIN "
        "RETURN (SELECT MAX(c.CustomerID) FROM Sales.Customer c WHERE c.StoreID = @s) END"
    )
    result, edges = run(
        catalog, definition, kind="scalar_function", output_columns=["RETURN_VALUE"]
    )
    assert edges == {
        ("self", None, "RETURN_VALUE", "Sales.Customer", "CustomerID", "inferred", "aggregate"),
    }
    assert refs(result, "read") == {"Sales.Customer"}


def test_update_with_xml_method_target_records_write_only(catalog):
    result, edges = run(
        catalog,
        proc(
            "UPDATE Sales.Customer SET StoreID.modify('replace value of (/x)[1] with 1') "
            "WHERE CustomerID = 1"
        ),
    )
    assert edges == set()
    assert refs(result, "write") == {"Sales.Customer"}
    assert result.issues == []


def test_scalar_function_variable_flow_select_assignment(catalog):
    definition = (
        "CREATE FUNCTION Sales.fnStore (@id int) RETURNS int AS BEGIN "
        "DECLARE @ret int "
        "SELECT @ret = MAX(c.StoreID) FROM Sales.Customer c WHERE c.CustomerID = @id "
        "RETURN @ret END"
    )
    _, edges = run(catalog, definition, kind="scalar_function", output_columns=["RETURN_VALUE"])
    assert edges == {
        ("self", None, "RETURN_VALUE", "Sales.Customer", "StoreID", "inferred", "aggregate"),
    }


def test_scalar_function_variable_flow_set_subquery(catalog):
    definition = (
        "CREATE FUNCTION Sales.fnName (@id int) RETURNS nvarchar(50) AS BEGIN "
        "DECLARE @n nvarchar(50) "
        "SET @n = (SELECT p.FirstName FROM Person.Person p WHERE p.BusinessEntityID = @id) "
        "SET @n = @n + '!' "
        "RETURN @n END"
    )
    _, edges = run(catalog, definition, kind="scalar_function", output_columns=["RETURN_VALUE"])
    assert edges == {
        ("self", None, "RETURN_VALUE", "Person.Person", "FirstName", "inferred", "expression"),
    }


def test_scalar_function_return_expression_of_variables(catalog):
    definition = (
        "CREATE FUNCTION Sales.fnBoth (@id int) RETURNS int AS BEGIN "
        "DECLARE @a int, @b int "
        "SELECT @a = c.StoreID, @b = c.PersonID FROM Sales.Customer c WHERE c.CustomerID = @id "
        "RETURN @a + @b END"
    )
    _, edges = run(catalog, definition, kind="scalar_function", output_columns=["RETURN_VALUE"])
    assert {(e[3], e[4]) for e in edges} == {
        ("Sales.Customer", "StoreID"),
        ("Sales.Customer", "PersonID"),
    }
    assert all(e[5] == "inferred" for e in edges)


def test_scalar_function_constant_reassignment_keeps_flow(catalog):
    definition = (
        "CREATE FUNCTION Sales.fnStock (@id int) RETURNS int AS BEGIN "
        "DECLARE @ret int "
        "SELECT @ret = SUM(c.StoreID) FROM Sales.Customer c WHERE c.PersonID = @id "
        "IF (@ret IS NULL) SET @ret = 0 "
        "RETURN @ret END"
    )
    _, edges = run(catalog, definition, kind="scalar_function", output_columns=["RETURN_VALUE"])
    assert edges == {
        ("self", None, "RETURN_VALUE", "Sales.Customer", "StoreID", "inferred", "aggregate"),
    }
