"""T-SQL statement splitting (sqlglot only splits on ';', T-SQL bodies rarely have them)."""

import pytest

from sqldoc.lineage.splitter import Statement, module_body, split_statements, view_query


def kinds(body: str) -> list[str]:
    return [s.kind for s in split_statements(body)]


def dml(body: str) -> list[str]:
    return [s.text for s in split_statements(body) if s.is_dml]


def test_semicolon_free_statements_split_on_keywords():
    assert kinds("SELECT 1 SELECT 2") == ["select", "select"]
    assert dml("SELECT 1\nSELECT 2") == ["SELECT 1", "SELECT 2"]


def test_offsets_slice_back_to_text():
    body = "SET NOCOUNT ON\nSELECT a FROM t\nUPDATE t SET a = 1"
    for s in split_statements(body):
        assert body[s.start : s.end] == s.text
    assert kinds(body) == ["set", "select", "update"]


def test_case_expression_does_not_split():
    body = "SELECT CASE WHEN a = 1 THEN 'x' ELSE 'y' END AS c, CASE a WHEN 2 THEN 1 END AS d FROM t"
    assert kinds(body) == ["select"]


def test_try_catch_blocks():
    body = "BEGIN TRY SELECT 1 END TRY BEGIN CATCH SELECT ERROR_MESSAGE() END CATCH"
    assert kinds(body) == ["begin", "select", "end", "begin", "select", "end"]
    assert dml(body) == ["SELECT 1", "SELECT ERROR_MESSAGE()"]


def test_update_set_is_one_statement():
    assert kinds("UPDATE t SET a = 1, b = 2 WHERE c = 3") == ["update"]
    assert kinds("UPDATE t SET a = s.a FROM t JOIN s ON s.id = t.id") == ["update"]


def test_insert_variants_are_single_statements():
    assert kinds("INSERT INTO t (a) SELECT a FROM s\nSELECT * FROM t") == ["insert", "select"]
    assert kinds("INSERT INTO t VALUES (1), (2)") == ["insert"]
    assert kinds("INSERT INTO t DEFAULT VALUES") == ["insert"]
    assert kinds("INSERT INTO t EXEC dbo.p @x = 1") == ["insert"]
    assert kinds("INSERT t (a) SELECT 1 UNION ALL SELECT 2") == ["insert"]


def test_set_operations_stay_together():
    assert kinds("SELECT 1 UNION ALL SELECT 2 EXCEPT SELECT 3 INTERSECT SELECT 4") == ["select"]
    assert kinds("SELECT 1 UNION\nSELECT 2") == ["select"]


def test_if_else_while_with_and_without_parens():
    assert kinds("IF (@x = 1) SELECT 1 ELSE SELECT 2") == ["if", "select", "else", "select"]
    assert kinds("IF @x = 1 SELECT 1") == ["if", "select"]
    assert kinds("IF EXISTS (SELECT 1 FROM t) SELECT 2") == ["if", "select"]
    assert kinds("WHILE @i < 10 BEGIN SET @i += 1 END") == ["while", "begin", "set", "end"]


def test_merge_runs_to_semicolon():
    body = (
        "MERGE INTO t USING s ON t.id = s.id "
        "WHEN MATCHED THEN UPDATE SET a = s.a "
        "WHEN NOT MATCHED THEN INSERT (a) VALUES (s.a); "
        "SELECT 1"
    )
    assert kinds(body) == ["merge", "select"]


def test_cte_prefixed_statements_take_the_dml_kind():
    assert kinds(";WITH c AS (SELECT 1 AS x) SELECT x FROM c") == ["select"]
    assert kinds("WITH c AS (SELECT 1 AS x) INSERT INTO t SELECT x FROM c") == ["insert"]
    assert kinds("WITH c AS (SELECT 1 AS x), d AS (SELECT 2 AS y) UPDATE t SET a = 1 FROM c") == [
        "update"
    ]


def test_declare_table_variable_and_cursor():
    table_var = "DECLARE @t TABLE (id int, name nvarchar(50)) INSERT INTO @t SELECT 1, 'a'"
    assert kinds(table_var) == ["declare", "insert"]
    assert kinds("DECLARE c CURSOR FOR SELECT a FROM t OPEN c FETCH NEXT FROM c INTO @a") == [
        "declare",
        "select",
        "open",
        "fetch",
    ]


def test_exec_variants():
    assert kinds("EXEC(@sql)") == ["exec"]
    assert kinds("EXEC sp_executesql @sql, N'@p int', @p = 1") == ["exec"]
    assert kinds("EXECUTE dbo.uspLogError @ErrorLogID OUTPUT") == ["exec"]
    stmts = split_statements("EXEC dbo.p 1 EXEC dbo.q 2")
    assert [s.kind for s in stmts] == ["exec", "exec"] and all(s.is_dml for s in stmts)


def test_comments_and_strings_are_inert():
    body = (
        "-- SELECT not a statement\n/* UPDATE nope */ "
        "SELECT '; SELECT 1' AS s, \"x\" FROM [dbo].[select]"
    )
    assert kinds(body) == ["select"]


def test_select_into_and_return():
    assert kinds("SELECT a INTO #t FROM s SELECT * FROM #t") == ["select", "select"]
    assert kinds("RETURN (SELECT 1)") == ["return"]
    assert kinds("RETURN @x") == ["return"]


def test_statement_indexes_and_dml_flag():
    stmts = split_statements("SET NOCOUNT ON SELECT 1 DELETE FROM t PRINT 'x'")
    assert [(s.index, s.kind, s.is_dml) for s in stmts] == [
        (0, "set", False),
        (1, "select", True),
        (2, "delete", True),
        (3, "print", False),
    ]
    assert isinstance(stmts[0], Statement)


def test_module_body_strips_create_header():
    proc = (
        "CREATE PROCEDURE dbo.p @a int = 1, @b varchar(10) OUTPUT\n"
        "WITH EXECUTE AS OWNER\nAS\nBEGIN\nSELECT 1\nEND"
    )
    assert module_body(proc).strip() == "BEGIN\nSELECT 1\nEND"
    fn = (
        "CREATE FUNCTION dbo.f (@a int) RETURNS @r TABLE (x int) "
        "AS BEGIN INSERT @r SELECT @a RETURN END"
    )
    assert module_body(fn).strip() == "BEGIN INSERT @r SELECT @a RETURN END"
    inline = "CREATE FUNCTION dbo.g(@a int) RETURNS TABLE AS RETURN (SELECT @a AS a)"
    assert module_body(inline).strip() == "RETURN (SELECT @a AS a)"
    trig = "CREATE TRIGGER Sales.trX ON Sales.T AFTER INSERT, UPDATE AS BEGIN SET NOCOUNT ON END"
    assert module_body(trig).strip() == "BEGIN SET NOCOUNT ON END"


def test_view_query_returns_select_after_header():
    view = (
        "CREATE VIEW [Sales].[vX] (a, b) WITH SCHEMABINDING AS\n"
        "SELECT c1, c2 FROM Sales.T\nWITH CHECK OPTION"
    )
    assert view_query(view) == "SELECT c1, c2 FROM Sales.T"
    cte = "CREATE VIEW v AS WITH c AS (SELECT 1 AS x) SELECT x FROM c"
    assert view_query(cte) == "WITH c AS (SELECT 1 AS x) SELECT x FROM c"


def test_unterminated_string_does_not_crash():
    stmts = split_statements("SELECT 'oops")
    assert len(stmts) == 1 and stmts[0].kind == "select"


@pytest.mark.parametrize("body", ["", "   ", "-- only a comment"])
def test_empty_bodies(body):
    assert split_statements(body) == []


def test_insert_output_and_hints_do_not_end_the_insert():
    assert kinds("INSERT INTO t (a) OUTPUT inserted.a INTO @log (a) SELECT x FROM s") == ["insert"]
    assert kinds("INSERT INTO t WITH (TABLOCK) (a) SELECT x FROM s SELECT 1") == [
        "insert",
        "select",
    ]


def test_trigger_update_predicate_is_not_a_statement():
    body = "IF UPDATE(ProductID) OR UPDATE(OrderQty) BEGIN SELECT 1 END UPDATE t SET a = 1"
    assert kinds(body) == ["if", "begin", "select", "end", "update"]


def test_try_catch_multiword_keywords_split_correctly():
    body = (
        "BEGIN TRY INSERT INTO t (a) SELECT 1 END TRY BEGIN CATCH EXECUTE dbo.p "
        "IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION END CATCH"
    )
    assert kinds(body) == ["begin", "insert", "end", "begin", "exec", "if", "rollback", "end"]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("END\nSELECT 1", ["end", "select"]),
        ("PRINT 'x' SELECT 1", ["print", "select"]),
        ("FETCH NEXT FROM c INTO @a SELECT 1", ["fetch", "select"]),
        ("END CATCH SELECT 1 END", ["end", "select", "end"]),
        (
            "IF @x = 1 BEGIN SELECT 1 END ELSE BEGIN SELECT 2 END SELECT 3",
            ["if", "begin", "select", "end", "else", "begin", "select", "end", "select"],
        ),
        ("PRINT N'unicode; with semicolon' SELECT 1", ["print", "select"]),
    ],
)
def test_command_mode_remainders_are_retokenized(body, expected):
    assert kinds(body) == expected
