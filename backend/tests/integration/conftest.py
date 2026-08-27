"""Integration fixtures: a live SQL Server (the AdventureWorks2022 docker container).

Tests are skipped unless localhost:1433 answers and a password is available via
SQLDOC_TEST_PASSWORD (or MSSQL_SA_PASSWORD, also read from the repo-root .env).
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from dotenv import load_dotenv

from sqldoc.config.schema import AuthCfg, ConnectionCfg, DatabaseCfg
from sqldoc.mssql.client import MssqlClient, connect

HOST, PORT, DATABASE = "localhost", 1433, "AdventureWorks2022"

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def _reachable() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            return True
    except OSError:
        return False


def _password() -> str | None:
    return os.environ.get("SQLDOC_TEST_PASSWORD") or os.environ.get("MSSQL_SA_PASSWORD")


def pytest_collection_modifyitems(config, items):
    reason = None
    if not _reachable():
        reason = f"no SQL Server at {HOST}:{PORT}"
    elif not _password():
        reason = "SQLDOC_TEST_PASSWORD / MSSQL_SA_PASSWORD not set"
    if reason:
        skip = pytest.mark.skip(reason=reason)
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def aw_connection_cfg() -> ConnectionCfg:
    return ConnectionCfg(
        name="test-aw",
        host=HOST,
        port=PORT,
        auth=AuthCfg(mode="sql", username="sa", password=_password() or ""),
        driver="pymssql",
        encrypt=False,
        databases=[DatabaseCfg(name=DATABASE, schemas=["Sales"])],
    )


@pytest.fixture(scope="session")
def aw_client(aw_connection_cfg) -> MssqlClient:
    client = connect(aw_connection_cfg, DATABASE)
    yield client
    client.close()
