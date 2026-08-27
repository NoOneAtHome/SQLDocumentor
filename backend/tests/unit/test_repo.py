"""store/repo: the read queries behind the API."""

import pytest

from sqldoc.store import models as m
from sqldoc.store import repo
from tests.unit import test_api_support as support
from tests.unit.test_api_support import CONN, DB

seeded = support.seeded


@pytest.fixture
def session(seeded):
    with seeded.runtime.db.session() as s:
        yield s


def test_scans(session, seeded):
    scans, total = repo.list_scans(session, CONN, limit=10, offset=0)
    assert total == 2 and [s.id for s in scans] == [seeded.seed.scan_id, seeded.seed.failed_scan_id]
    assert repo.latest_scan(session, CONN).id == seeded.seed.scan_id
    assert repo.latest_scan(session, "dw") is None
    assert repo.list_scans(session, "dw", 10, 0) == ([], 0)


def test_list_objects_filters_sort_and_paging(session, seeded):
    sid = seeded.seed.scan_id
    objs, total = repo.list_objects(session, sid, repo.ObjectFilter())
    assert total == 8 and [o.name for o in objs][:2] == ["Address", "Customer"]
    objs, total = repo.list_objects(session, sid, repo.ObjectFilter(schema="sales"))
    assert total == 4 and all(o.schema_name == "Sales" for o in objs)
    objs, total = repo.list_objects(session, sid, repo.ObjectFilter(kind="table,view"))
    assert {o.kind for o in objs} == {"table", "view"} and total == 4
    objs, _ = repo.list_objects(session, sid, repo.ObjectFilter(scope="external"))
    assert [o.name for o in objs] == ["Remote"]
    objs, _ = repo.list_objects(session, sid, repo.ObjectFilter(q="cust"))
    assert {o.name for o in objs} == {"Customer", "vCustomer", "uspUpdateCustomer", "trCustomer"}
    objs, _ = repo.list_objects(session, sid, repo.ObjectFilter(tag="PII"))
    assert [o.name for o in objs] == ["Person"]
    objs, _ = repo.list_objects(session, sid, repo.ObjectFilter(has_issues=True))
    assert {o.name for o in objs} == {"uspUpdateCustomer", "trCustomer"}
    objs, _ = repo.list_objects(session, sid, repo.ObjectFilter(sort="rows", order="desc"))
    assert [o.name for o in objs][:3] == ["Person", "Customer", "Address"]
    objs, _ = repo.list_objects(session, sid, repo.ObjectFilter(sort="size", order="desc"))
    assert [o.name for o in objs][:2] == ["Person", "Customer"]
    objs, total = repo.list_objects(session, sid, repo.ObjectFilter(limit=2, offset=2))
    assert total == 8 and len(objs) == 2 and objs[0].name == "Person"


def test_lookup_is_case_insensitive(session, seeded):
    sid = seeded.seed.scan_id
    o = repo.lookup_object(session, sid, "aw", "SALES", "vcustomer")
    assert o is not None and o.id == seeded.seed.ids["view"]
    assert repo.lookup_object(session, sid, "AW", "Sales", "nope") is None
    assert repo.get_object(session, sid, seeded.seed.ids["view"]).name == "vCustomer"
    assert repo.get_object(session, sid + 100, seeded.seed.ids["view"]) is None


def test_summary_extras_annotations_and_tags(session, seeded):
    seed = seeded.seed
    extras = repo.summary_extras(session, seed.scan_id, list(seed.ids.values()))
    assert extras[seed.ids["customer"]]["row_count"] == 19820
    assert extras[seed.ids["customer"]]["total_size_kb"] == 1600
    assert extras[seed.ids["proc"]]["exec_count"] == 42
    assert extras[seed.ids["proc"]]["has_lineage_issues"] is True
    assert extras[seed.ids["view"]]["has_lineage_issues"] is False
    keys = [f"{CONN}|{DB}|Sales|Customer", f"{CONN}|{DB}|Person|Person"]
    ann = repo.annotations_for_keys(session, "object", keys)
    assert ann[keys[0].casefold()].description == "Customer master (user)"
    tags = repo.tags_for_keys(session, "object", keys)
    assert tags[keys[0].casefold()] == ["core"] and tags[keys[1].casefold()] == ["pii"]


def test_detail_parts(session, seeded):
    seed = seeded.seed
    sid, cid = seed.scan_id, seed.ids["customer"]
    cols = repo.columns_for(session, sid, cid)
    assert [c.name for c in cols] == ["CustomerID", "PersonID", "AccountNumber", "ModifiedDate"]
    indexes = repo.indexes_for(session, sid, cid)
    assert [i.index.name for i in indexes] == ["PK_Customer_CustomerID", "IX_Customer_PersonID"]
    assert [c.column_name for c in indexes[1].columns] == ["PersonID", "AccountNumber"]
    assert indexes[1].usage.is_unused is True
    fks_out = repo.foreign_keys_for(session, sid, cid, direction="out")
    assert len(fks_out) == 1 and fks_out[0].fk.name == "FK_Customer_Person_PersonID"
    assert fks_out[0].columns[0].referenced_column_name == "BusinessEntityID"
    fks_in = repo.foreign_keys_for(session, sid, seed.ids["person"], direction="in")
    assert [f.fk.name for f in fks_in] == ["FK_Customer_Person_PersonID"]
    assert [t.name for t in repo.triggers_for(session, sid, cid)] == ["trCustomer"]
    assert repo.table_stats_for(session, sid, cid).row_count == 19820
    assert repo.proc_stats_for(session, sid, seed.ids["proc"]).execution_count == 42
    assert len(repo.missing_indexes_for(session, sid, cid)) == 1
    uses, used_by = repo.dependencies_for(session, sid, seed.ids["proc"])
    assert {(d.target.name if d.target else None, d.dep.resolution) for d in uses} == {
        ("Customer", "resolved"),
        ("Person", "resolved"),
        ("ufnLeadingZeros", "caller_dependent"),
        ("Remote", "external"),
        (None, "ambiguous"),
    }
    assert {d.source.name for d in used_by} == {"trCustomer"}
    counts = repo.column_lineage_counts(session, sid, cid)
    assert counts[seed.cols[("customer", "CustomerID")]] == (0, 2)
    assert counts[seed.cols[("customer", "AccountNumber")]] == (2, 0)
    assert counts[seed.cols[("customer", "PersonID")]] == (1, 0)
    issues = repo.lineage_issues_for(session, sid, seed.ids["proc"])
    assert [i.kind for i in issues] == ["dynamic_sql"]
    assert [p.name for p in repo.parameters_for(session, sid, seed.ids["proc"])] == [
        "@CustomerID",
        "@Name",
    ]
    assert [c.name for c in repo.check_constraints_for(session, sid, cid)] == [
        "CK_Customer_CustomerID"
    ]


def test_search(session, seeded):
    sid = seeded.seed.scan_id
    hits = repo.search_objects(session, sid, "customer", limit=10)
    assert {o.name for o in hits} == {"Customer", "vCustomer", "uspUpdateCustomer", "trCustomer"}
    defs = repo.search_definitions(session, sid, "UPPER(", limit=10)
    assert [o.name for o in defs] == ["uspUpdateCustomer"]
    cols = repo.search_columns(session, sid, "firstname", limit=10)
    assert {(o.name, c.name) for c, o in cols} == {
        ("vCustomer", "FirstName"),
        ("Person", "FirstName"),
    }


def test_stats_queries(session, seeded):
    sid = seeded.seed.scan_id
    rows, total = repo.stats_tables(session, sid, sort="rows", order="desc", limit=10, offset=0)
    assert total == 3 and [o.name for _, o in rows] == ["Person", "Customer", "Address"]
    rows, total = repo.stats_tables(session, sid, schema="Person", limit=10, offset=0)
    assert total == 2
    rows, total = repo.stats_indexes(session, sid, unused=True, limit=10, offset=0)
    assert total == 1 and rows[0][1].name == "IX_Customer_PersonID"
    rows, total = repo.stats_indexes(session, sid, sort="seeks", order="desc", limit=2, offset=0)
    assert total == 4 and [r[1].name for r in rows] == [
        "PK_Customer_CustomerID",
        "PK_Person_BusinessEntityID",
    ]
    rows, total = repo.stats_procs(session, sid, limit=10, offset=0)
    assert total == 2 and rows[0][1].name == "uspUpdateCustomer"
    rows, total = repo.stats_missing_indexes(session, sid, limit=10, offset=0)
    assert total == 2 and rows[0][1].name == "Person"


def test_scan_overview_and_lineage_summary(session, seeded):
    sid = seeded.seed.scan_id
    ov = repo.scan_overview(session, sid)
    assert [d["name"] for d in ov["databases"]] == [DB]
    schemas = {s["name"]: s for s in ov["databases"][0]["schemas"]}
    assert schemas["Sales"]["is_selected"] and not schemas["Person"]["is_selected"]
    assert schemas["Sales"]["counts_by_kind"] == {
        "table": 1,
        "view": 1,
        "procedure": 1,
        "trigger": 1,
    }
    assert ov["warnings_summary"] == {
        "lineage_issues": 2,
        "unused_indexes": 1,
        "missing_index_suggestions": 2,
        "external_refs": 1,
    }
    assert ov["lineage_coverage"] == pytest.approx(0.75)  # ok, partial, failed, ok -> 3/4
    ls = repo.lineage_summary(session, sid)
    assert ls["edges_by_kind"]["catalog"] == 8 and ls["edges_by_kind"]["parsed_write"] == 1
    assert ls["column_edges_by_confidence"] == {"exact": 2, "inferred": 2, "unresolved": 1}
    assert ls["objects_with_issues"] == 2


def test_annotations_roundtrip(session, seeded):
    key = f"{CONN}|{DB}|Person|Address"
    ann = repo.upsert_annotation(session, "object", key, description="Addresses", notes=None)
    assert ann.description == "Addresses" and ann.notes is None
    repo.set_tags(session, "object", key, ["Geo", "core"])
    assert repo.tag_names_for(session, "object", key) == ["core", "Geo"]
    repo.set_tags(session, "object", key, ["geo"])  # case-insensitive dedupe on tags
    assert repo.tag_names_for(session, "object", key) == ["Geo"]
    ann = repo.upsert_annotation(session, "object", key, description=None)
    assert ann.description is None
    entries, total = repo.list_annotations(
        session, connection=CONN, tag="geo", q=None, limit=10, offset=0
    )
    assert total == 1 and entries[0].target_key == key
    tags = repo.list_tags(session, connection=CONN)
    assert {(t.name, t.count) for t in tags} >= {("core", 1), ("pii", 2), ("Geo", 1)}
    assert repo.delete_annotation(session, "object", key) is True
    assert repo.delete_annotation(session, "object", key) is False
    assert repo.tag_names_for(session, "object", key) == []
    session.rollback()


def test_delete_scan_cascades(seeded):
    db = seeded.runtime.db
    with db.session() as s:
        scan = m.Scan(connection_name="tmp", status="failed", started_at=m.utcnow())
        s.add(scan)
        s.flush()
        s.add(m.ScanWarning(scan_id=scan.id, phase="connect", code="x", message="y"))
        s.commit()
        sid = scan.id
    with db.session() as s:
        assert repo.delete_scan(s, sid) is True
        s.commit()
        assert s.get(m.Scan, sid) is None
        assert repo.delete_scan(s, sid) is False
