"""create_app: health, config, OpenAPI surface, CORS, SPA mount."""

from sqldoc import __version__
from tests.unit import test_api_support as support

seeded = support.seeded
client = support.client


def test_health(client, seeded):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["version"] == __version__
    assert body["db_path"].endswith("api.sqlite")


def test_config_is_sanitized(client, seeded):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["config_path"].endswith("sqldoc.yaml")
    assert body["sqlite_path"].endswith("api.sqlite")
    text = r.text
    assert "hunter2" not in text
    assert body["config"]["connections"][0]["name"] == "local"
    assert body["config"]["connections"][0]["auth"]["password"] == "**********"


def test_openapi_exposes_contract_schemas_and_paths(client):
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    for name in (
        "ObjectSummary",
        "ObjectDetail",
        "Column",
        "Index",
        "TableStats",
        "ExecStats",
        "MissingIndex",
        "ScanSummary",
        "LineageGraph",
        "LineageNode",
        "LineageEdge",
        "ColumnLineageGraph",
        "ColumnLineageNode",
        "ColumnLineageEdge",
        "Annotation",
    ):
        assert name in schemas, name
    paths = spec["paths"]
    for path in (
        "/api/connections",
        "/api/connections/{name}/test",
        "/api/connections/{name}/scans",
        "/api/scans/{scan_id}",
        "/api/scans/{scan_id}/cancel",
        "/api/scans/{scan_id}/summary",
        "/api/scans/{scan_id}/objects",
        "/api/scans/{scan_id}/objects/lookup",
        "/api/scans/{scan_id}/objects/{object_id}",
        "/api/scans/{scan_id}/objects/{object_id}/definition",
        "/api/scans/{scan_id}/search",
        "/api/scans/{scan_id}/lineage/objects",
        "/api/scans/{scan_id}/lineage/columns",
        "/api/scans/{scan_id}/lineage/objects/{object_id}/columns",
        "/api/scans/{scan_id}/lineage/summary",
        "/api/scans/{scan_id}/lineage/issues",
        "/api/scans/{scan_id}/stats/tables",
        "/api/scans/{scan_id}/stats/indexes",
        "/api/scans/{scan_id}/stats/procs",
        "/api/scans/{scan_id}/stats/missing-indexes",
        "/api/annotations",
        "/api/tags",
        "/api/health",
        "/api/config",
    ):
        assert path in paths, path
    # optional fields are nullable so generated TS types carry `| null`
    assert "null" in str(schemas["ObjectSummary"]["properties"]["row_count"])


def test_cors_allows_vite_dev_server(client):
    r = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_api_route_is_json_404_not_spa(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["detail"] == "Not Found"


def test_frontend_mount_is_low_priority(client):
    # No built SPA in the test environment: the fallback is a 404, never a 500,
    # and API routes still win.
    assert client.get("/some/spa/route").status_code in (200, 404)
    assert client.get("/api/health").status_code == 200
