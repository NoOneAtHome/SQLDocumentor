"""Driver selection and connection construction.

Two DB-API drivers are supported behind one tiny surface:

* ``pyodbc`` + Microsoft ODBC Driver 18 - required for integrated (Kerberos /
  SSPI) authentication and enforced TLS. Needs the system ODBC driver.
* ``pymssql`` (bundled FreeTDS) - zero system dependencies; SQL logins only.
  TLS is negotiated best-effort by FreeTDS and certificates are not validated.

``driver: auto`` (the default) picks pyodbc when it is importable *and* the
Microsoft driver is registered, otherwise pymssql.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from sqldoc.config.schema import ConnectionCfg

ODBC_DRIVER_NAME = "ODBC Driver 18 for SQL Server"
APP_NAME = "sqldoc"

DriverKind = Literal["pyodbc", "pymssql"]


class DriverUnavailable(Exception):
    """The requested (or required) driver cannot be used on this machine."""


@dataclass(frozen=True)
class Driver:
    name: DriverKind
    paramstyle: str
    connect: Callable[[ConnectionCfg, str, str | None], Any]


def odbc_escape(value: str) -> str:
    """Quote an ODBC connection-string value when it contains special characters."""
    if any(ch in value for ch in ";{} "):
        return "{" + value.replace("}", "}}") + "}"
    return value


def build_odbc_connection_string(cfg: ConnectionCfg, database: str, secret: str | None) -> str:
    parts: dict[str, str] = {
        "DRIVER": "{" + ODBC_DRIVER_NAME + "}",
        "SERVER": f"tcp:{cfg.host},{cfg.port}",
        "DATABASE": database,
        "Encrypt": "yes" if cfg.encrypt else "no",
        "TrustServerCertificate": "yes" if cfg.trust_server_certificate else "no",
        "APP": APP_NAME,
        "Connection Timeout": str(cfg.connect_timeout_seconds),
    }
    if cfg.auth.mode == "sql":
        parts["UID"] = cfg.auth.username or ""
        parts["PWD"] = odbc_escape(secret or "")
    else:
        parts["Trusted_Connection"] = "yes"
    return ";".join(f"{k}={v}" for k, v in parts.items())


def build_pymssql_kwargs(cfg: ConnectionCfg, database: str, secret: str | None) -> dict[str, Any]:
    return {
        "server": cfg.host,
        "port": cfg.port,
        "user": cfg.auth.username,
        "password": secret,
        "database": database,
        "appname": APP_NAME,
        "login_timeout": cfg.connect_timeout_seconds,
        "timeout": cfg.query_timeout_seconds,
        "tds_version": "7.4",
        "autocommit": True,
        "encryption": "require" if cfg.encrypt else "off",
    }


def _connect_pyodbc(cfg: ConnectionCfg, database: str, secret: str | None) -> Any:
    pyodbc = importlib.import_module("pyodbc")
    conn = pyodbc.connect(
        build_odbc_connection_string(cfg, database, secret),
        autocommit=True,
        timeout=cfg.connect_timeout_seconds,
    )
    conn.timeout = cfg.query_timeout_seconds
    return conn


def _connect_pymssql(cfg: ConnectionCfg, database: str, secret: str | None) -> Any:
    pymssql = importlib.import_module("pymssql")
    return pymssql.connect(**build_pymssql_kwargs(cfg, database, secret))


PYODBC = Driver(name="pyodbc", paramstyle="qmark", connect=_connect_pyodbc)
PYMSSQL = Driver(name="pymssql", paramstyle="pyformat", connect=_connect_pymssql)


def pyodbc_ready() -> bool:
    """True when pyodbc imports and the Microsoft ODBC driver is registered."""
    try:
        pyodbc = importlib.import_module("pyodbc")
    except Exception:  # ImportError, or a dlopen failure surfacing as ImportError/OSError
        return False
    try:
        return any("ODBC Driver" in d and "SQL Server" in d for d in pyodbc.drivers())
    except Exception:
        return False


def select_driver(cfg: ConnectionCfg, pyodbc_ready: bool | None = None) -> Driver:
    ready = globals()["pyodbc_ready"]() if pyodbc_ready is None else pyodbc_ready
    if cfg.driver == "pymssql":
        if cfg.auth.mode == "integrated":
            raise DriverUnavailable(
                f"connection '{cfg.name}': integrated authentication requires the pyodbc driver"
            )
        return PYMSSQL
    if cfg.driver == "pyodbc" or cfg.auth.mode == "integrated":
        if not ready:
            reason = (
                "integrated authentication requires pyodbc"
                if cfg.auth.mode == "integrated"
                else "driver 'pyodbc' was requested"
            )
            raise DriverUnavailable(
                f"connection '{cfg.name}': {reason}, but pyodbc and/or '{ODBC_DRIVER_NAME}' "
                "are not available. Install with `uv sync --extra odbc` and the Microsoft ODBC "
                "driver (macOS: brew tap microsoft/mssql-release && brew install msodbcsql18)."
            )
        return PYODBC
    return PYODBC if ready else PYMSSQL


def diagnostics() -> dict[str, Any]:
    """What drivers can this machine use? Surfaced by `sqldoc connections test`."""
    info: dict[str, Any] = {"pymssql": False, "pyodbc": False, "odbc_drivers": []}
    try:
        pymssql = importlib.import_module("pymssql")
        info["pymssql"] = pymssql.__version__
    except Exception as exc:
        info["pymssql_error"] = str(exc)
    try:
        pyodbc = importlib.import_module("pyodbc")
        info["pyodbc"] = pyodbc.version
        info["odbc_drivers"] = list(pyodbc.drivers())
    except Exception as exc:
        info["pyodbc_error"] = str(exc).splitlines()[0]
    info["pyodbc_ready"] = pyodbc_ready()
    return info
