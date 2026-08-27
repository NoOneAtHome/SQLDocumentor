"""MssqlClient behaviour over a fake DB-API connection."""

from sqldoc.mssql.client import MssqlClient, quote_ident


class FakeCursor:
    def __init__(self, log, rows, description):
        self.log, self._rows, self.description = log, rows, description

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows=(), description=()):
        self.log = []
        self.rows, self.description = list(rows), list(description)
        self.closed = False

    def cursor(self):
        return FakeCursor(self.log, self.rows, self.description)

    def close(self):
        self.closed = True


def test_quote_ident_escapes_closing_bracket():
    assert quote_ident("Sales") == "[Sales]"
    assert quote_ident("we]ird") == "[we]]ird]"


def test_query_returns_rows_as_dicts_keyed_by_column_name():
    conn = FakeConnection(rows=[(1, "a"), (2, "b")], description=[("id",), ("name",)])
    client = MssqlClient(conn, paramstyle="qmark")
    rows = client.query("SELECT 1")
    assert rows == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    assert conn.log == [("SELECT 1", None)]


def test_query_translates_qmark_params_for_pyformat_drivers():
    conn = FakeConnection(rows=[], description=[])
    client = MssqlClient(conn, paramstyle="pyformat")
    client.query("SELECT * FROM t WHERE a = ? AND b LIKE '%x%' AND c = ?", (1, 2))
    sql, params = conn.log[0]
    assert sql == "SELECT * FROM t WHERE a = %s AND b LIKE '%%x%%' AND c = %s"
    assert params == (1, 2)


def test_query_leaves_sql_untouched_without_params_on_pyformat():
    conn = FakeConnection(rows=[], description=[])
    client = MssqlClient(conn, paramstyle="pyformat")
    client.query("SELECT '%' AS pct, '?' AS q")
    assert conn.log[0] == ("SELECT '%' AS pct, '?' AS q", None)


def test_use_database_quotes_and_tracks_current():
    conn = FakeConnection()
    client = MssqlClient(conn, paramstyle="qmark")
    client.use_database("Adventure]Works")
    assert conn.log == [("USE [Adventure]]Works]", None)]
    assert client.current_database == "Adventure]Works"


def test_close_closes_connection():
    conn = FakeConnection()
    MssqlClient(conn, paramstyle="qmark").close()
    assert conn.closed
