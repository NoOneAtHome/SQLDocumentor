"""Catalog endpoints: object listing, detail, lookup, definition, search."""

from tests.unit import test_api_support as support

seeded = support.seeded
client = support.client


def test_objects_listing_defaults(client, seeded):
    sid = seeded.seed.scan_id
    r = client.get(f"/api/scans/{sid}/objects")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 8 and body["limit"] == 50 and body["offset"] == 0
    by_name = {o["name"]: o for o in body["items"]}
    customer = by_name["Customer"]
    assert customer["id"] == seeded.seed.ids["customer"]
    assert customer["object_key"] == "local|AW|Sales|Customer"
    assert customer["db"] == "AW" and customer["schema"] == "Sales"
    assert customer["kind"] == "table" and customer["scope"] == "in_scope"
    assert customer["description"] == "Customer master data."
    assert customer["annotation_description"] == "Customer master (user)"
    assert customer["tags"] == ["core"]
    assert customer["row_count"] == 19820 and customer["total_size_kb"] == 1600
    assert customer["exec_count"] is None
    assert customer["modified_at"].startswith("2021-01-02")
    assert customer["lineage_status"] == "n/a" and customer["has_lineage_issues"] is False
    proc = by_name["uspUpdateCustomer"]
    assert proc["exec_count"] == 42 and proc["has_lineage_issues"] is True
    assert proc["lineage_status"] == "partial" and proc["row_count"] is None
    assert by_name["Person"]["tags"] == ["pii"] and by_name["Person"]["scope"] == "cascaded"
    assert by_name["Remote"]["scope"] == "external" and by_name["Remote"]["db"] == "OtherDb"
    assert r.headers["cache-control"] == "no-cache"


def test_objects_listing_filters_and_sort(client, seeded):
    sid = seeded.seed.scan_id
    base = f"/api/scans/{sid}/objects"
    assert client.get(base, params={"schema": "Sales"}).json()["total"] == 4
    assert client.get(base, params={"db": "aw", "schema": "person"}).json()["total"] == 2
    assert client.get(base, params={"kind": "table"}).json()["total"] == 3
    assert client.get(base, params={"kind": "table,view"}).json()["total"] == 4
    assert client.get(base, params={"scope": "cascaded"}).json()["total"] == 3
    assert client.get(base, params={"q": "upd"}).json()["items"][0]["name"] == "uspUpdateCustomer"
    assert [o["name"] for o in client.get(base, params={"tag": "core"}).json()["items"]] == [
        "Customer"
    ]
    assert client.get(base, params={"has_issues": "true"}).json()["total"] == 2
    assert client.get(base, params={"has_issues": "false"}).json()["total"] == 6
    rows = client.get(base, params={"sort": "rows", "order": "desc"}).json()["items"]
    assert [o["name"] for o in rows[:3]] == ["Person", "Customer", "Address"]
    modified = client.get(base, params={"sort": "modified", "order": "desc"}).json()["items"]
    assert modified[0]["name"] == "ufnLeadingZeros"
    page = client.get(base, params={"limit": 3, "offset": 3}).json()
    assert page["total"] == 8 and len(page["items"]) == 3 and page["offset"] == 3
    assert client.get(base, params={"sort": "bogus"}).status_code == 422
    assert client.get("/api/scans/999999/objects").status_code == 404


def test_object_detail_composite(client, seeded):
    seed = seeded.seed
    sid, cid = seed.scan_id, seed.ids["customer"]
    r = client.get(f"/api/scans/{sid}/objects/{cid}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["summary"]["name"] == "Customer" and d["summary"]["tags"] == ["core"]
    assert d["sql_object_id"] == 1 and d["ms_description"] == "Customer master data."
    assert d["created_at"].startswith("2020-01-01") and d["modified_at"].startswith("2021-01-02")
    assert d["parent"] is None

    cols = {c["name"]: c for c in d["columns"]}
    assert list(cols) == ["CustomerID", "PersonID", "AccountNumber", "ModifiedDate"]
    cust_id = cols["CustomerID"]
    assert cust_id["ordinal"] == 1 and cust_id["type_display"] == "int"
    assert cust_id["is_identity"] and cust_id["in_primary_key"]
    assert cust_id["ms_description"] == "Primary key." and cust_id["description"] == "Surrogate key"
    assert cust_id["lineage"] == {"upstream": 0, "downstream": 2}
    assert cust_id["fk_to"] is None and cust_id["column_kind"] == "column"
    person = cols["PersonID"]
    assert person["is_nullable"] and not person["in_primary_key"]
    assert person["fk_to"] == {
        "object_id": seed.ids["person"],
        "schema": "Person",
        "name": "Person",
        "column": "BusinessEntityID",
    }
    assert person["lineage"] == {"upstream": 1, "downstream": 0}
    acct = cols["AccountNumber"]
    assert acct["is_computed"] and acct["computed_definition"].startswith("(isnull")
    assert acct["type_display"] == "varchar(10)"
    assert cols["ModifiedDate"]["default_definition"] == "(getdate())"

    assert d["parameters"] == []
    idx = {i["name"]: i for i in d["indexes"]}
    assert idx["PK_Customer_CustomerID"]["is_primary_key"]
    assert idx["PK_Customer_CustomerID"]["key_columns"] == [{"name": "CustomerID", "desc": False}]
    assert idx["PK_Customer_CustomerID"]["usage"]["seeks"] == 100
    ix = idx["IX_Customer_PersonID"]
    assert ix["key_columns"] == [{"name": "PersonID", "desc": False}]
    assert ix["included_columns"] == ["AccountNumber"] and ix["is_unused"] is True
    assert ix["usage"]["updates"] == 20 and ix["description"] == "Lookup by person."

    keys = d["keys"]
    assert keys["primary_key"] == {
        "name": "PK_Customer_CustomerID",
        "type_desc": "CLUSTERED",
        "columns": ["CustomerID"],
    }
    assert keys["unique_constraints"] == []
    fk_out = keys["foreign_keys_out"][0]
    assert fk_out["name"] == "FK_Customer_Person_PersonID"
    assert fk_out["referenced"]["name"] == "Person" and fk_out["parent"]["name"] == "Customer"
    assert fk_out["columns"] == [{"column": "PersonID", "referenced_column": "BusinessEntityID"}]
    assert keys["foreign_keys_in"] == []
    assert keys["check_constraints"][0]["definition"] == "([CustomerID]>(0))"
    assert keys["check_constraints"][0]["column"] == "CustomerID"

    assert d["triggers"] == [
        {
            "id": seed.ids["trig"],
            "name": "trCustomer",
            "events": "UPDATE",
            "is_instead_of": False,
            "is_disabled": False,
        }
    ]
    assert d["stats"]["kind"] == "table" and d["stats"]["row_count"] == 19820
    assert d["stats"]["compression"] == "NONE" and d["stats"]["stats_as_of"]
    assert d["missing_indexes"][0]["equality_columns"] == "[PersonID]"
    assert d["missing_indexes"][0]["improvement_measure"] == 4200.0
    assert d["missing_indexes"][0]["suggested_ddl"].startswith("CREATE NONCLUSTERED INDEX")

    uses = {(u["name"], u["edge_kind"]) for u in d["dependencies"]["uses"]}
    assert uses == {("Person", "fk"), ("ufnLeadingZeros", "catalog")}
    used_by = {(u["name"], u["edge_kind"]) for u in d["dependencies"]["used_by"]}
    assert used_by == {
        ("vCustomer", "catalog"),
        ("trCustomer", "trigger"),
        ("uspUpdateCustomer", "catalog"),
        ("uspUpdateCustomer", "parsed_write"),
    }
    # data-flow counts: feeds = Person(fk), trigger, proc(write), fn(computed col)
    assert d["lineage_counts"] == {"upstream": 4, "downstream": 2, "columns_with_lineage": 3}
    assert d["lineage_issues"] == []
    assert d["annotation"]["description"] == "Customer master (user)"
    assert d["annotation"]["notes"] == "Owned by the CRM team"
    assert d["annotation"]["tags"] == ["core"]
    assert d["column_annotations"]["CustomerID"]["description"] == "Surrogate key"
    assert set(d["column_annotations"]) == {"CustomerID"}
    assert r.headers["cache-control"] == "no-cache"


def test_object_detail_for_proc_trigger_and_external(client, seeded):
    seed = seeded.seed
    sid = seed.scan_id
    d = client.get(f"/api/scans/{sid}/objects/{seed.ids['proc']}").json()
    assert [p["name"] for p in d["parameters"]] == ["@CustomerID", "@Name"]
    assert d["parameters"][1]["type_display"] == "nvarchar(100)"
    assert d["stats"]["kind"] == "exec" and d["stats"]["exec_count"] == 42
    assert d["stats"]["avg_ms"] == 100.0 and d["stats"]["total_ms"] == 4200.0
    assert d["stats"]["since_server_start"] is not None
    assert d["lineage_issues"] == [
        {
            "kind": "dynamic_sql",
            "statement_index": 2,
            "message": "EXEC(@sql): dynamic SQL is not analyzed",
            "snippet": "EXEC(@sql)",
        }
    ]
    uses = {(u["name"], u["resolution"]) for u in d["dependencies"]["uses"]}
    assert ("Remote", "external") in uses and ("value", "ambiguous") in uses
    unresolved = next(u for u in d["dependencies"]["uses"] if u["resolution"] == "ambiguous")
    assert unresolved["object_id"] is None and unresolved["referenced_name"] == "value"
    assert d["summary"]["has_lineage_issues"] is True
    assert d["annotation"] is None and d["column_annotations"] == {}

    t = client.get(f"/api/scans/{sid}/objects/{seed.ids['trig']}").json()
    assert t["parent"] == {
        "id": seed.ids["customer"],
        "schema": "Sales",
        "name": "Customer",
        "kind": "table",
    }
    assert t["stats"] is None

    fn = client.get(f"/api/scans/{sid}/objects/{seed.ids['fn']}").json()
    assert fn["parameters"][0]["is_return_value"] and fn["parameters"][0]["name"] == ""
    assert fn["parameters"][0]["description"] == "Zero-padded value."

    ext = client.get(f"/api/scans/{sid}/objects/{seed.ids['remote']}").json()
    assert ext["summary"]["kind"] == "external" and ext["columns"] == []
    assert {u["name"] for u in ext["dependencies"]["used_by"]} == {"uspUpdateCustomer"}


def test_lookup_by_name_case_insensitive(client, seeded):
    sid = seeded.seed.scan_id
    r = client.get(
        f"/api/scans/{sid}/objects/lookup",
        params={"db": "aw", "schema": "sales", "name": "VCUSTOMER"},
    )
    assert r.status_code == 200
    assert r.json()["summary"]["id"] == seeded.seed.ids["view"]
    r = client.get(
        f"/api/scans/{sid}/objects/lookup", params={"db": "AW", "schema": "Sales", "name": "nope"}
    )
    assert r.status_code == 404
    assert client.get(f"/api/scans/{sid}/objects/999999").status_code == 404
    assert client.get(f"/api/scans/999999/objects/{seeded.seed.ids['view']}").status_code == 404


def test_definition(client, seeded):
    sid, pid = seeded.seed.scan_id, seeded.seed.ids["proc"]
    r = client.get(f"/api/scans/{sid}/objects/{pid}/definition")
    assert r.status_code == 200
    body = r.json()
    assert body["definition"].startswith("CREATE PROCEDURE") and body["has_dynamic_sql"] is True
    assert body["length"] == len(body["definition"])
    assert r.headers["cache-control"] == "max-age=86400"
    table = client.get(f"/api/scans/{sid}/objects/{seeded.seed.ids['customer']}/definition").json()
    assert table["definition"] is None and table["length"] == 0


def test_search(client, seeded):
    sid = seeded.seed.scan_id
    r = client.get(f"/api/scans/{sid}/search", params={"q": "first"})
    assert r.status_code == 200
    body = r.json()
    assert body["objects"] == []
    assert {(c["object"]["name"], c["column"], c["data_type"]) for c in body["columns"]} == {
        ("vCustomer", "FirstName", "nvarchar(50)"),
        ("Person", "FirstName", "nvarchar(50)"),
    }
    body = client.get(f"/api/scans/{sid}/search", params={"q": "customer", "limit": 3}).json()
    assert len(body["objects"]) == 3 and body["objects"][0]["match"]["field"] == "name"
    body = client.get(
        f"/api/scans/{sid}/search", params={"q": "UPPER(", "kinds": "object,definition"}
    ).json()
    assert [o["name"] for o in body["objects"]] == ["uspUpdateCustomer"]
    assert body["objects"][0]["match"]["field"] == "definition"
    assert "UPPER(" in body["objects"][0]["match"]["snippet"] and body["columns"] == []
    assert client.get(f"/api/scans/{sid}/search", params={"q": ""}).status_code == 422
