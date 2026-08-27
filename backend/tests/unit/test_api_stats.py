"""Stats grids."""

from tests.unit import test_api_support as support

seeded = support.seeded
client = support.client


def test_tables_grid(client, seeded):
    sid = seeded.seed.scan_id
    r = client.get(f"/api/scans/{sid}/stats/tables")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3 and [i["object"]["name"] for i in body["items"]] == [
        "Person",
        "Customer",
        "Address",
    ]  # default sort: reserved_kb desc
    row = body["items"][1]
    assert row["object"]["tags"] == ["core"] and row["row_count"] == 19820
    assert row["data_kb"] == 1024 and row["index_kb"] == 512 and row["reserved_kb"] == 1600
    assert row["partition_count"] == 1 and row["is_heap"] is False and row["compression"] == "NONE"
    body = client.get(
        f"/api/scans/{sid}/stats/tables", params={"sort": "rows", "order": "asc"}
    ).json()
    assert [i["object"]["name"] for i in body["items"]] == ["Address", "Customer", "Person"]
    body = client.get(f"/api/scans/{sid}/stats/tables", params={"schema": "Person"}).json()
    assert body["total"] == 2
    body = client.get(
        f"/api/scans/{sid}/stats/tables", params={"db": "AW", "limit": 1, "offset": 1}
    ).json()
    assert body["total"] == 3 and body["items"][0]["object"]["name"] == "Customer"
    assert r.headers["cache-control"] == "no-cache"
    assert client.get("/api/scans/999999/stats/tables").status_code == 404


def test_indexes_grid(client, seeded):
    sid = seeded.seed.scan_id
    body = client.get(f"/api/scans/{sid}/stats/indexes").json()
    assert body["total"] == 4
    body = client.get(f"/api/scans/{sid}/stats/indexes", params={"unused": "true"}).json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["object"]["name"] == "Customer" and row["index_name"] == "IX_Customer_PersonID"
    assert row["type_desc"] == "NONCLUSTERED" and row["is_unused"] is True
    assert row["seeks"] == 0 and row["updates"] == 20 and row["last_update"] is not None
    assert row["key_columns"] == ["PersonID"] and row["included_columns"] == ["AccountNumber"]
    body = client.get(
        f"/api/scans/{sid}/stats/indexes", params={"sort": "seeks", "order": "desc"}
    ).json()
    assert body["items"][0]["index_name"] == "PK_Customer_CustomerID"
    body = client.get(f"/api/scans/{sid}/stats/indexes", params={"schema": "Sales"}).json()
    assert body["total"] == 2


def test_procs_grid(client, seeded):
    sid = seeded.seed.scan_id
    body = client.get(f"/api/scans/{sid}/stats/procs").json()
    assert body["total"] == 2 and body["items"][0]["object"]["name"] == "uspUpdateCustomer"
    row = body["items"][0]
    assert row["exec_count"] == 42 and row["total_ms"] == 4200.0 and row["avg_ms"] == 100.0
    assert row["max_ms"] == 300.0 and row["total_cpu_ms"] == 2000.0
    assert row["total_logical_reads"] == 1234 and row["last_exec_at"] is not None
    body = client.get(
        f"/api/scans/{sid}/stats/procs", params={"sort": "exec_count", "order": "asc"}
    ).json()
    assert body["items"][0]["object"]["name"] == "ufnLeadingZeros"
    body = client.get(f"/api/scans/{sid}/stats/procs", params={"schema": "dbo"}).json()
    assert body["total"] == 1


def test_missing_indexes_grid(client, seeded):
    sid = seeded.seed.scan_id
    body = client.get(f"/api/scans/{sid}/stats/missing-indexes").json()
    assert body["total"] == 2 and body["items"][0]["object"]["name"] == "Person"
    row = body["items"][1]
    assert row["object"]["name"] == "Customer" and row["equality_columns"] == "[PersonID]"
    assert row["included_columns"] == "[AccountNumber]" and row["user_seeks"] == 5
    assert row["avg_cost"] == 10.5 and row["avg_impact"] == 80.0
    assert row["improvement_measure"] == 4200.0
    assert row["suggested_ddl"].startswith("CREATE NONCLUSTERED INDEX")
    body = client.get(
        f"/api/scans/{sid}/stats/missing-indexes", params={"sort": "seeks", "order": "asc"}
    ).json()
    assert body["items"][0]["object"]["name"] == "Customer"
    assert (
        client.get(f"/api/scans/{sid}/stats/missing-indexes", params={"schema": "Sales"}).json()[
            "total"
        ]
        == 1
    )
