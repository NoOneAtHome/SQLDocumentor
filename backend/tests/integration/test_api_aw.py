"""Every API router once, against a real AdventureWorks2022 scan."""

import pytest
from fastapi.testclient import TestClient

from sqldoc.api.app import create_app
from sqldoc.config.schema import AppConfig, ScanOptions
from sqldoc.runtime import Runtime
from sqldoc.scan.manager import ScanManager
from sqldoc.store.db import Database

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api(tmp_path_factory, aw_connection_cfg):
    tmp = tmp_path_factory.mktemp("api")
    db = Database.open(tmp / "aw.sqlite")
    cfg = AppConfig(connections=[aw_connection_cfg], scan=ScanOptions(parse_lineage=False))
    mgr = ScanManager(db, cfg)
    scan_id = mgr.start(aw_connection_cfg.name)
    assert mgr.wait(scan_id, timeout=180)
    assert mgr.progress(scan_id)["status"] == "succeeded", mgr.progress(scan_id)
    config_path = tmp / "sqldoc.yaml"
    config_path.write_text("version: 1\n")
    rt = Runtime(cfg=cfg, db=db, manager=mgr, config_path=config_path)
    with TestClient(create_app(rt)) as client:
        yield client, scan_id, mgr


def test_connections_and_scans(api):
    client, scan_id, _ = api
    conns = client.get("/api/connections").json()["items"]
    assert conns[0]["name"] == "test-aw" and conns[0]["latest_scan"]["id"] == scan_id
    assert conns[0]["latest_scan"]["counts"]["tables"] > 19
    status = client.get(f"/api/scans/{scan_id}").json()
    assert status["status"] == "succeeded" and status["progress"]["phase"] == "finalize"
    summary = client.get(f"/api/scans/{scan_id}/summary").json()
    schemas = {s["name"]: s for s in summary["databases"][0]["schemas"]}
    assert schemas["Sales"]["is_selected"] and not schemas["Person"]["is_selected"]
    assert schemas["Sales"]["counts_by_kind"]["table"] == 19
    assert summary["warnings_summary"]["missing_index_suggestions"] >= 0
    test = client.post("/api/connections/test-aw/test").json()
    assert test["ok"] is True and test["version"].startswith("16.")
    assert test["databases"][0]["reachable"] and test["auth_scheme"] == "SQL"


def test_objects_listing_for_sales(api):
    client, scan_id, _ = api
    body = client.get(
        f"/api/scans/{scan_id}/objects", params={"schema": "Sales", "kind": "table", "limit": 100}
    ).json()
    assert body["total"] == 19
    names = {o["name"] for o in body["items"]}
    assert {"Customer", "SalesOrderHeader", "SalesOrderDetail"} <= names
    customer = next(o for o in body["items"] if o["name"] == "Customer")
    assert customer["row_count"] == 19820 and customer["scope"] == "in_scope"
    assert customer["description"]  # MS_Description
    by_rows = client.get(
        f"/api/scans/{scan_id}/objects", params={"sort": "rows", "order": "desc", "limit": 1}
    ).json()
    assert by_rows["items"][0]["name"] == "SalesOrderDetail"
    search = client.get(f"/api/scans/{scan_id}/search", params={"q": "individualcust"}).json()
    assert [o["name"] for o in search["objects"]] == ["vIndividualCustomer"]


def test_lookup_and_detail_of_view(api):
    client, scan_id, _ = api
    r = client.get(
        f"/api/scans/{scan_id}/objects/lookup",
        params={"db": "adventureworks2022", "schema": "sales", "name": "vindividualcustomer"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["summary"]["name"] == "vIndividualCustomer" and d["summary"]["kind"] == "view"
    assert {c["name"] for c in d["columns"]} >= {"FirstName", "LastName", "AddressLine1"}
    uses = {u["name"] for u in d["dependencies"]["uses"]}
    assert {"Person", "Customer", "Address"} <= uses
    assert d["lineage_counts"]["upstream"] >= 5
    definition = client.get(f"/api/scans/{scan_id}/objects/{d['summary']['id']}/definition").json()
    assert definition["definition"].upper().lstrip().startswith("CREATE VIEW")

    cust = client.get(
        f"/api/scans/{scan_id}/objects/lookup",
        params={"db": "AdventureWorks2022", "schema": "Sales", "name": "Customer"},
    ).json()
    assert cust["stats"]["kind"] == "table" and cust["stats"]["row_count"] == 19820
    assert {f["name"] for f in cust["keys"]["foreign_keys_out"]} >= {
        "FK_Customer_Person_PersonID",
        "FK_Customer_Store_StoreID",
    }
    assert cust["keys"]["primary_key"]["columns"] == ["CustomerID"]
    assert any(i["usage"] is not None for i in cust["indexes"])
    assert {t["name"] for t in cust["triggers"]} == set() or cust["triggers"]
    person_id = next(c for c in cust["columns"] if c["name"] == "PersonID")
    assert person_id["fk_to"]["name"] == "Person"


def test_object_lineage_graph(api):
    client, scan_id, _ = api
    view = client.get(
        f"/api/scans/{scan_id}/objects/lookup",
        params={"db": "AdventureWorks2022", "schema": "Sales", "name": "vIndividualCustomer"},
    ).json()["summary"]
    g = client.get(
        f"/api/scans/{scan_id}/lineage/objects",
        params={"focus": view["id"], "direction": "both", "depth": 2},
    ).json()
    names = {(n["schema"], n["name"]): n for n in g["nodes"]}
    assert ("Person", "Person") in names and names[("Person", "Person")]["hop"] < 0
    assert names[("Sales", "vIndividualCustomer")]["hop"] == 0
    assert all(e["source"] != e["target"] for e in g["edges"])
    cols = client.get(f"/api/scans/{scan_id}/lineage/objects/{view['id']}/columns").json()
    assert {c["name"] for c in cols} >= {"FirstName"}
    summary = client.get(f"/api/scans/{scan_id}/lineage/summary").json()
    assert summary["edges_by_kind"]["fk"] > 0 and summary["edges_by_kind"]["trigger"] > 0
    assert client.get(f"/api/scans/{scan_id}/lineage/issues").json()["total"] == 0
    cg = client.get(f"/api/scans/{scan_id}/lineage/columns", params={"focus": view["id"]}).json()
    assert cg["focus"]["object_id"] == view["id"]  # no column lineage parsed in this scan


def test_stats_grids(api):
    client, scan_id, _ = api
    tables = client.get(f"/api/scans/{scan_id}/stats/tables", params={"limit": 5}).json()
    assert (
        tables["total"] > 19
        and tables["items"][0]["reserved_kb"] >= tables["items"][1]["reserved_kb"]
    )
    indexes = client.get(f"/api/scans/{scan_id}/stats/indexes", params={"unused": "true"}).json()
    assert all(i["is_unused"] for i in indexes["items"])
    procs = client.get(f"/api/scans/{scan_id}/stats/procs").json()
    assert procs["total"] >= 0
    missing = client.get(f"/api/scans/{scan_id}/stats/missing-indexes").json()
    assert missing["total"] >= 0


def test_annotation_survives_second_scan(api):
    client, first, mgr = api
    key = {
        "connection": "test-aw",
        "db": "AdventureWorks2022",
        "schema": "Sales",
        "name": "Customer",
    }
    r = client.put(
        "/api/annotations", json={**key, "description": "Customer master", "tags": ["core"]}
    )
    assert r.status_code == 200 and r.json()["tags"] == ["core"]
    second = mgr.start("test-aw")
    assert mgr.wait(second, timeout=180)
    conns = client.get("/api/connections").json()["items"]
    assert conns[0]["latest_scan"]["id"] == second
    cust = client.get(
        f"/api/scans/{second}/objects/lookup",
        params={"db": "AdventureWorks2022", "schema": "Sales", "name": "Customer"},
    ).json()
    assert cust["summary"]["annotation_description"] == "Customer master"
    assert cust["summary"]["tags"] == ["core"]
    tags = client.get("/api/tags", params={"connection": "test-aw"}).json()
    assert {"tag": "core", "color": None, "count": 1} in tags
    assert client.delete("/api/annotations", params=key).status_code == 204
