"""Annotations & tags: upsert/clear/delete/list keyed by object_key, surviving scans."""

from tests.unit import test_api_support as support

seeded = support.seeded
client = support.client

KEY = {"connection": "local", "db": "AW", "schema": "Person", "name": "Address"}


def test_put_creates_annotation_with_tags(client, seeded):
    r = client.put(
        "/api/annotations",
        json={**KEY, "description": "Postal addresses", "notes": "n1", "tags": ["Geo", "core"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_kind"] == "object" and body["target_key"] == "local|AW|Person|Address"
    assert body["connection"] == "local" and body["db"] == "AW" and body["schema"] == "Person"
    assert body["name"] == "Address" and body["column"] is None
    assert body["description"] == "Postal addresses" and body["notes"] == "n1"
    assert body["tags"] == ["core", "Geo"]
    assert body["created_at"] and body["updated_at"]

    # visible on the object summary in the snapshot, matched by object_key
    sid = seeded.seed.scan_id
    detail = client.get(f"/api/scans/{sid}/objects/{seeded.seed.ids['address']}").json()
    assert detail["summary"]["annotation_description"] == "Postal addresses"
    assert detail["summary"]["tags"] == ["core", "Geo"]
    assert detail["annotation"]["notes"] == "n1"


def test_put_partial_update_and_null_clears(client):
    body = client.put("/api/annotations", json={**KEY, "notes": "n2"}).json()
    assert body["description"] == "Postal addresses" and body["notes"] == "n2"
    assert body["tags"] == ["core", "Geo"]  # untouched when omitted
    body = client.put("/api/annotations", json={**KEY, "description": None}).json()
    assert body["description"] is None and body["notes"] == "n2"
    body = client.put("/api/annotations", json={**KEY, "tags": []}).json()
    assert body["tags"] == []
    body = client.put("/api/annotations", json={**KEY, "tags": ["geo", "GEO"]}).json()
    assert body["tags"] == ["Geo"]  # tags are case-insensitive; existing spelling wins


def test_column_annotation_key(client, seeded):
    r = client.put(
        "/api/annotations",
        json={**KEY, "column": "City", "description": "City name", "tags": ["pii"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["target_kind"] == "column"
    assert body["target_key"] == "local|AW|Person|Address|City" and body["column"] == "City"
    sid = seeded.seed.scan_id
    detail = client.get(f"/api/scans/{sid}/objects/{seeded.seed.ids['address']}").json()
    assert detail["column_annotations"]["City"]["description"] == "City name"
    assert detail["column_annotations"]["City"]["tags"] == ["pii"]
    city = next(c for c in detail["columns"] if c["name"] == "City")
    assert city["description"] == "City name" and city["ms_description"] is None


def test_list_and_tags(client):
    r = client.get("/api/annotations", params={"connection": "local"})
    assert r.status_code == 200
    body = r.json()
    keys = {a["target_key"] for a in body["items"]}
    assert {
        "local|AW|Sales|Customer",
        "local|AW|Sales|Customer|CustomerID",
        "local|AW|Person|Person",
        "local|AW|Person|Person|FirstName",
        "local|AW|Person|Address",
        "local|AW|Person|Address|City",
    } <= keys
    assert body["total"] == len(body["items"])
    person = next(a for a in body["items"] if a["target_key"] == "local|AW|Person|Person")
    assert person["description"] is None and person["tags"] == ["pii"]  # tag-only target
    body = client.get("/api/annotations", params={"tag": "pii"}).json()
    assert {a["target_key"] for a in body["items"]} == {
        "local|AW|Person|Person",
        "local|AW|Person|Person|FirstName",
        "local|AW|Person|Address|City",
    }
    body = client.get("/api/annotations", params={"q": "crm"}).json()
    assert [a["target_key"] for a in body["items"]] == ["local|AW|Sales|Customer"]
    assert client.get("/api/annotations", params={"connection": "dw"}).json()["total"] == 0
    page = client.get("/api/annotations", params={"limit": 2, "offset": 1}).json()
    assert len(page["items"]) == 2 and page["offset"] == 1

    tags = {t["tag"]: t for t in client.get("/api/tags", params={"connection": "local"}).json()}
    assert tags["pii"]["count"] == 3 and tags["pii"]["color"] == "#ef4444"
    assert tags["core"]["count"] == 1 and tags["Geo"]["count"] == 1
    assert client.get("/api/tags", params={"connection": "dw"}).json() == [
        {"tag": "core", "color": "#3b82f6", "count": 0},
        {"tag": "Geo", "color": None, "count": 0},
        {"tag": "pii", "color": "#ef4444", "count": 0},
    ]


def test_delete(client, seeded):
    r = client.delete("/api/annotations", params={**KEY, "column": "City"})
    assert r.status_code == 204
    assert client.delete("/api/annotations", params={**KEY, "column": "City"}).status_code == 404
    r = client.delete("/api/annotations", params=KEY)
    assert r.status_code == 204
    keys = {a["target_key"] for a in client.get("/api/annotations").json()["items"]}
    assert "local|AW|Person|Address" not in keys and "local|AW|Person|Address|City" not in keys
    sid = seeded.seed.scan_id
    detail = client.get(f"/api/scans/{sid}/objects/{seeded.seed.ids['address']}").json()
    assert detail["annotation"] is None and detail["summary"]["tags"] == []


def test_validation(client):
    assert client.put("/api/annotations", json={"connection": "local"}).status_code == 422
    r = client.put("/api/annotations", json={**KEY, "tags": ["", "  "]})
    assert r.status_code == 200 and r.json()["tags"] == []
