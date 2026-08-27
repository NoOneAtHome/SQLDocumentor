"""GET /api/connections and POST /api/connections/{name}/test."""

from sqldoc.api.routers import connections as connections_router
from tests.unit import test_api_support as support

seeded = support.seeded
client = support.client


def test_list_connections_with_latest_scan(client, seeded):
    r = client.get("/api/connections")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    local, dw = body["items"]
    assert local["name"] == "local" and local["host"] == "localhost" and local["port"] == 1433
    assert local["auth_mode"] == "sql" and local["username"] == "sa"
    assert local["databases"] == [{"name": "AW", "schemas": ["Sales"]}]
    assert local["latest_scan"]["id"] == seeded.seed.scan_id
    assert local["latest_scan"]["status"] == "succeeded"
    assert local["latest_scan"]["counts"]["tables"] == 3
    assert local["running_scan_id"] is None
    assert dw["auth_mode"] == "integrated" and dw["latest_scan"] is None
    assert "hunter2" not in r.text


class FakeClient:
    driver_name = "pymssql"

    def __init__(self, fail_db: str | None = None):
        self.fail_db = fail_db
        self.current_database = None
        self.closed = False

    def query(self, sql, params=None):
        if "SERVERPROPERTY" in sql:
            return [
                {
                    "product_version": "16.0.4000.1",
                    "edition": "Developer Edition",
                    "server_name": "SQLBOX",
                }
            ]
        if "HAS_PERMS_BY_NAME" in sql:
            return [{"view_server_state": 1, "view_database_state": 1, "view_definition": 0}]
        return []

    def scalar(self, sql, params=None):
        return "SQL"

    def use_database(self, name):
        if name == self.fail_db:
            raise RuntimeError(f"Cannot open database {name}")
        self.current_database = name

    def close(self):
        self.closed = True


def test_connection_test_success(client, monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(connections_router, "connect", lambda cfg, database: fake)
    r = client.post("/api/connections/local/test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["server_name"] == "SQLBOX" and body["version"] == "16.0.4000.1"
    assert body["edition"] == "Developer Edition" and body["auth_scheme"] == "SQL"
    assert body["driver"] == "pymssql" and body["can_view_server_state"] is True
    assert body["databases"] == [
        {
            "name": "AW",
            "reachable": True,
            "can_view_definition": False,
            "can_view_database_state": True,
            "error": None,
        }
    ]
    assert body["error"] is None and fake.closed


def test_connection_test_failure_is_not_a_500(client, monkeypatch):
    def boom(cfg, database):
        raise RuntimeError("Login failed for user 'sa'")

    monkeypatch.setattr(connections_router, "connect", boom)
    r = client.post("/api/connections/local/test")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and "Login failed" in body["error"]
    assert body["databases"][0]["reachable"] is False


def test_connection_test_partial_database_failure(client, monkeypatch):
    fake = FakeClient(fail_db="AW")
    monkeypatch.setattr(connections_router, "connect", lambda cfg, database: fake)
    body = client.post("/api/connections/local/test").json()
    assert body["ok"] is True
    assert body["databases"][0]["reachable"] is False
    assert "Cannot open database" in body["databases"][0]["error"]


def test_connection_test_unknown_connection(client):
    assert client.post("/api/connections/nope/test").status_code == 404
