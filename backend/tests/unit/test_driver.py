"""Driver selection and connection construction (no live server)."""

import pytest

from sqldoc.config.schema import AuthCfg, ConnectionCfg, DatabaseCfg
from sqldoc.mssql.driver import (
    DriverUnavailable,
    build_odbc_connection_string,
    build_pymssql_kwargs,
    odbc_escape,
    select_driver,
)


def conn_cfg(**overrides) -> ConnectionCfg:
    base = dict(
        name="c",
        host="db.example.com",
        port=1433,
        auth=AuthCfg(mode="sql", username="sa", password="p w}d"),
        databases=[DatabaseCfg(name="AW", schemas=["Sales"])],
    )
    base.update(overrides)
    return ConnectionCfg(**base)


def test_odbc_escape_wraps_and_doubles_braces():
    assert odbc_escape("plain") == "plain"
    assert odbc_escape("p;w") == "{p;w}"
    assert odbc_escape("a}b") == "{a}}b}"
    assert odbc_escape("a b") == "{a b}"


def test_odbc_string_sql_auth():
    s = build_odbc_connection_string(conn_cfg(), database="AW", secret="p w}d")
    parts = dict(p.split("=", 1) for p in s.split(";"))
    assert parts["DRIVER"] == "{ODBC Driver 18 for SQL Server}"
    assert parts["SERVER"] == "tcp:db.example.com,1433"
    assert parts["DATABASE"] == "AW"
    assert parts["UID"] == "sa"
    assert parts["PWD"] == "{p w}}d}"
    assert parts["Encrypt"] == "yes"
    assert parts["TrustServerCertificate"] == "no"
    assert parts["APP"] == "sqldoc"
    assert "Trusted_Connection" not in parts


def test_odbc_string_integrated_auth_has_no_credentials():
    cfg = conn_cfg(auth=AuthCfg(mode="integrated"), trust_server_certificate=True, encrypt=False)
    s = build_odbc_connection_string(cfg, database="AW", secret=None)
    parts = dict(p.split("=", 1) for p in s.split(";"))
    assert parts["Trusted_Connection"] == "yes"
    assert "UID" not in parts and "PWD" not in parts
    assert parts["Encrypt"] == "no"
    assert parts["TrustServerCertificate"] == "yes"


def test_pymssql_kwargs():
    kw = build_pymssql_kwargs(conn_cfg(), database="AW", secret="pw")
    assert kw["server"] == "db.example.com"
    assert kw["port"] == 1433
    assert kw["user"] == "sa"
    assert kw["password"] == "pw"
    assert kw["database"] == "AW"
    assert kw["appname"] == "sqldoc"
    assert kw["login_timeout"] == 15
    assert kw["encryption"] == "require"
    kw = build_pymssql_kwargs(conn_cfg(encrypt=False), database="AW", secret="pw")
    assert kw["encryption"] == "off"


def test_select_driver_explicit_pymssql():
    assert select_driver(conn_cfg(driver="pymssql"), pyodbc_ready=True).name == "pymssql"


def test_select_driver_auto_prefers_pyodbc_when_ready():
    assert select_driver(conn_cfg(driver="auto"), pyodbc_ready=True).name == "pyodbc"
    assert select_driver(conn_cfg(driver="auto"), pyodbc_ready=False).name == "pymssql"


def test_select_driver_integrated_requires_pyodbc():
    cfg = conn_cfg(auth=AuthCfg(mode="integrated"), driver="auto")
    with pytest.raises(DriverUnavailable) as exc:
        select_driver(cfg, pyodbc_ready=False)
    assert "integrated" in str(exc.value)
    assert "pyodbc" in str(exc.value)


def test_select_driver_explicit_pyodbc_when_missing_is_error():
    with pytest.raises(DriverUnavailable):
        select_driver(conn_cfg(driver="pyodbc"), pyodbc_ready=False)
