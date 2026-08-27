"""Lineage endpoints: object ego graph, column graph, per-object columns, summary, issues."""

from tests.unit import test_api_support as support

seeded = support.seeded
client = support.client


def nodes_by_name(graph):
    return {n["name"]: n for n in graph["nodes"]}


def test_object_graph_upstream_of_view(client, seeded):
    seed = seeded.seed
    sid = seed.scan_id
    r = client.get(
        f"/api/scans/{sid}/lineage/objects",
        params={"focus": seed.ids["view"], "direction": "up", "depth": 1},
    )
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["focus"] == f"o:{seed.ids['view']}"
    assert g["truncated"] is False and g["total"] == 3
    nodes = nodes_by_name(g)
    assert set(nodes) == {"vCustomer", "Customer", "Person"}
    view = nodes["vCustomer"]
    assert view["id"] == f"o:{seed.ids['view']}" and view["hop"] == 0
    assert view["object_id"] == seed.ids["view"] and view["db"] == "AW"
    assert view["schema"] == "Sales" and view["kind"] == "view" and view["scope"] == "in_scope"
    assert view["row_count"] is None and view["exec_count"] is None
    assert view["has_lineage_issues"] is False and view["more"] == {"upstream": 0, "downstream": 0}
    customer = nodes["Customer"]
    assert customer["hop"] == -1 and customer["row_count"] == 19820
    assert customer["more"] == {"upstream": 3, "downstream": 1}  # trigger, fn, proc / proc
    assert nodes["Person"]["scope"] == "cascaded" and nodes["Person"]["more"] == {
        "upstream": 1,
        "downstream": 1,
    }
    edges = {(e["source"], e["target"], e["kind"]) for e in g["edges"]}
    o = lambda k: f"o:{seed.ids[k]}"  # noqa: E731
    assert edges == {
        (o("customer"), o("view"), "catalog"),
        (o("person"), o("view"), "catalog"),
        (o("person"), o("customer"), "fk"),
    }
    fk_edge = next(e for e in g["edges"] if e["kind"] == "fk")
    assert (
        fk_edge["detail"] == "FK_Customer_Person_PersonID" and fk_edge["resolution"] == "resolved"
    )
    assert fk_edge["id"].startswith("e:")
    assert r.headers["cache-control"] == "max-age=86400"


def test_object_graph_depth_filters_and_truncation(client, seeded):
    seed = seeded.seed
    sid = seed.scan_id
    base = f"/api/scans/{sid}/lineage/objects"
    g = client.get(base, params={"focus": seed.ids["view"], "direction": "up", "depth": 2}).json()
    assert set(nodes_by_name(g)) == {
        "vCustomer",
        "Customer",
        "Person",
        "Address",
        "trCustomer",
        "ufnLeadingZeros",
        "uspUpdateCustomer",
    }
    assert nodes_by_name(g)["Address"]["hop"] == -2
    assert nodes_by_name(g)["uspUpdateCustomer"]["exec_count"] == 42
    assert nodes_by_name(g)["uspUpdateCustomer"]["has_lineage_issues"] is True

    g = client.get(
        base,
        params={
            "focus": seed.ids["proc"],
            "direction": "up",
            "depth": 1,
            "include_external": False,
        },
    ).json()
    assert "Remote" not in nodes_by_name(g)
    g = client.get(base, params={"focus": seed.ids["proc"], "direction": "up", "depth": 1}).json()
    assert nodes_by_name(g)["Remote"]["scope"] == "external"

    g = client.get(
        base, params={"focus": seed.ids["view"], "direction": "up", "depth": 2, "kinds": "table"}
    ).json()
    assert set(nodes_by_name(g)) == {"vCustomer", "Customer", "Person", "Address"}
    g = client.get(
        base, params={"focus": seed.ids["view"], "depth": 2, "include_cascaded": False}
    ).json()
    assert "Person" not in nodes_by_name(g)
    g = client.get(
        base,
        params={"focus": seed.ids["customer"], "direction": "up", "depth": 2, "edge_kinds": "fk"},
    ).json()
    assert set(nodes_by_name(g)) == {"Customer", "Person", "Address"}
    g = client.get(
        base, params={"focus": seed.ids["view"], "direction": "up", "depth": 2, "schemas": "Sales"}
    ).json()
    assert set(nodes_by_name(g)) == {"vCustomer", "Customer", "trCustomer", "uspUpdateCustomer"}

    g = client.get(
        base, params={"focus": seed.ids["view"], "direction": "up", "depth": 2, "max_nodes": 3}
    ).json()
    assert g["truncated"] is True and g["total"] == 7 and len(g["nodes"]) == 3
    assert set(nodes_by_name(g)) == {"vCustomer", "Customer", "Person"}

    down = client.get(base, params={"focus": seed.ids["person"], "direction": "down"}).json()
    assert {n["name"]: n["hop"] for n in down["nodes"]} == {
        "Person": 0,
        "vCustomer": 1,
        "Customer": 1,
        "uspUpdateCustomer": 1,
    }
    assert client.get(base, params={"focus": 999999}).status_code == 404
    assert client.get(base, params={"focus": seed.ids["view"], "depth": 9}).status_code == 422
    assert (
        client.get(base, params={"focus": seed.ids["view"], "direction": "sideways"}).status_code
        == 422
    )
    assert client.get(base).status_code == 422


def test_column_graph_grouped_by_object(client, seeded):
    seed = seeded.seed
    sid = seed.scan_id
    base = f"/api/scans/{sid}/lineage/columns"
    r = client.get(base, params={"focus": seed.ids["view"], "direction": "up", "depth": 1})
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["focus"] == {"object_id": seed.ids["view"], "column": None}
    assert g["truncated"] is False and g["total"] == 3
    nodes = nodes_by_name(g)
    assert set(nodes) == {"vCustomer", "Customer", "Person"}
    view = nodes["vCustomer"]
    assert view["hop"] == 0 and view["column_count_total"] == 2
    assert [c["name"] for c in view["columns"]] == ["CustomerID", "FirstName"]
    assert view["columns"][0]["column_id"] == seed.cols[("view", "CustomerID")]
    assert view["columns"][0]["data_type"] == "int"
    assert "row_count" not in view and view["more"] == {"upstream": 0, "downstream": 0}
    assert [c["name"] for c in nodes["Customer"]["columns"]] == ["CustomerID"]
    assert nodes["Customer"]["column_count_total"] == 4
    assert [c["name"] for c in nodes["Person"]["columns"]] == ["FirstName"]
    edges = {(e["source"], e["source_column"], e["target"], e["target_column"]) for e in g["edges"]}
    o = lambda k: f"o:{seed.ids[k]}"  # noqa: E731
    assert edges == {
        (o("person"), "FirstName", o("view"), "FirstName"),
        (o("customer"), "CustomerID", o("view"), "CustomerID"),
    }
    e = next(e for e in g["edges"] if e["source_column"] == "FirstName")
    assert e["confidence"] == "exact" and e["transform"] == "passthrough"
    assert e["via_object_id"] is None and e["via_name"] is None and e["expression"] == "p.FirstName"
    assert e["id"].startswith("c:")
    assert r.headers["cache-control"] == "max-age=86400"

    # single column seed
    g = client.get(
        base, params={"focus": seed.ids["view"], "column": "firstname", "direction": "up"}
    ).json()
    assert g["focus"]["column"] == "FirstName"
    assert set(nodes_by_name(g)) == {"vCustomer", "Person"}

    # proc appears only as via on the edge into Customer.AccountNumber
    g = client.get(
        base, params={"focus": seed.ids["customer"], "direction": "up", "depth": 1}
    ).json()
    names = set(nodes_by_name(g))
    assert "uspUpdateCustomer" not in names and names == {"Customer", "Person"}
    via = next(
        e for e in g["edges"] if e["target_column"] == "AccountNumber" and e["via_object_id"]
    )
    assert via["via_object_id"] == seed.ids["proc"] and via["via_name"] == "Sales.uspUpdateCustomer"
    assert via["confidence"] == "inferred" and via["expression"] == "UPPER(p.FirstName)"
    # intra-table computed edge is present too
    assert any(
        e["source_column"] == "CustomerID" and e["target_column"] == "AccountNumber"
        for e in g["edges"]
    )
    exact = client.get(
        base, params={"focus": seed.ids["customer"], "direction": "up", "min_confidence": "exact"}
    ).json()
    assert set(nodes_by_name(exact)) == {"Customer"} and exact["edges"] == []

    assert client.get(base, params={"focus": seed.ids["view"], "column": "nope"}).status_code == 404
    assert client.get(base, params={"focus": 999999}).status_code == 404


def test_object_columns_lineage_counts(client, seeded):
    seed = seeded.seed
    r = client.get(f"/api/scans/{seed.scan_id}/lineage/objects/{seed.ids['customer']}/columns")
    assert r.status_code == 200
    rows = {c["name"]: c for c in r.json()}
    assert rows["CustomerID"]["column_id"] == seed.cols[("customer", "CustomerID")]
    assert (rows["CustomerID"]["upstream_count"], rows["CustomerID"]["downstream_count"]) == (0, 2)
    assert rows["CustomerID"]["confidences"] == {"exact": 1, "inferred": 1, "unresolved": 0}
    assert rows["AccountNumber"]["upstream_count"] == 2
    assert rows["PersonID"]["confidences"] == {"exact": 0, "inferred": 0, "unresolved": 1}
    assert rows["ModifiedDate"]["upstream_count"] == 0
    assert (
        client.get(f"/api/scans/{seed.scan_id}/lineage/objects/999999/columns").status_code == 404
    )


def test_lineage_summary_and_issues(client, seeded):
    seed = seeded.seed
    r = client.get(f"/api/scans/{seed.scan_id}/lineage/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["objects"] == 8
    assert body["edges_by_kind"]["catalog"] == 8 and body["edges_by_kind"]["fk"] == 2
    assert body["column_edges_by_confidence"] == {"exact": 2, "inferred": 2, "unresolved": 1}
    assert body["lineage_coverage"] == 0.75 and body["objects_with_issues"] == 2
    hubs = body["top_hubs"]
    assert hubs[0]["name"] == "Customer" and hubs[0]["degree"] == 6
    assert hubs[0]["upstream"] == 4 and hubs[0]["downstream"] == 2

    r = client.get(f"/api/scans/{seed.scan_id}/lineage/issues")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert [i["object"]["name"] for i in body["items"]] == ["trCustomer", "uspUpdateCustomer"]
    assert body["items"][1]["kind"] == "dynamic_sql" and body["items"][1]["snippet"] == "EXEC(@sql)"
    assert body["items"][1]["object"]["schema"] == "Sales"
    assert (
        client.get(f"/api/scans/{seed.scan_id}/lineage/issues?limit=1&offset=1").json()["items"][0][
            "kind"
        ]
        == "dynamic_sql"
    )
