"""Catalog queries against the live AdventureWorks2022 sample database."""

import pytest

from sqldoc.mssql.catalog import CatalogExtractor, RawDatabase

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def raw(aw_client) -> RawDatabase:
    ex = CatalogExtractor(aw_client)
    db = RawDatabase(name="AdventureWorks2022", info=ex.database_info())
    db.objects = ex.objects()
    db.triggers = ex.triggers()
    db.synonyms = ex.synonyms()
    db.dependencies = ex.dependencies()
    db.foreign_keys = ex.foreign_keys()
    return ex.details(db)


def by_name(raw: RawDatabase, schema: str, name: str) -> dict:
    return next(o for o in raw.objects if o["schema_name"] == schema and o["name"] == name)


def test_database_info(raw):
    assert raw.info["name"] == "AdventureWorks2022"
    assert raw.info["collation_name"]


def test_object_counts(raw):
    kinds = {}
    for o in raw.objects:
        kinds[o["type"]] = kinds.get(o["type"], 0) + 1
    assert kinds["U"] == 71
    assert kinds["V"] == 20
    assert kinds["P"] == 10
    assert kinds["FN"] == 10
    assert kinds["TF"] == 1
    assert kinds["TR"] == 10
    assert all(o["type"] == o["type"].strip() for o in raw.objects)


def test_detail_counts(raw):
    user_table_and_view_cols = [
        c for c in raw.columns if c["object_id"] in {o["object_id"] for o in raw.objects}
    ]
    assert len(user_table_and_view_cols) == 749
    assert len(raw.foreign_keys) == 90
    assert len(raw.indexes) == 175
    assert len(raw.dependencies) == 323  # referencing_class = 1 only
    assert len([e for e in raw.extended_properties if e["class"] == 1]) == 1008
    assert len(raw.modules) == 51  # views + procs + functions + triggers


def test_computed_column_definition(raw):
    sod = by_name(raw, "Sales", "SalesOrderDetail")
    line_total = next(
        c for c in raw.columns if c["object_id"] == sod["object_id"] and c["name"] == "LineTotal"
    )
    assert line_total["is_computed"]
    assert "UnitPrice" in line_total["computed_definition"]


def test_trigger_events_and_instead_of(raw):
    idu = next(t for t in raw.triggers if t["name"] == "iduSalesOrderDetail")
    assert set(idu["events"].split(",")) == {"INSERT", "UPDATE", "DELETE"}
    assert not idu["is_instead_of_trigger"]
    d_emp = next(t for t in raw.triggers if t["name"] == "dEmployee")
    assert d_emp["is_instead_of_trigger"]


def test_function_return_value_parameter(raw):
    fn = by_name(raw, "dbo", "ufnGetAccountingEndDate")
    ret = next(
        p for p in raw.parameters if p["object_id"] == fn["object_id"] and p["parameter_id"] == 0
    )
    assert ret["name"] in ("", None)
    assert ret["type_name"] == "datetime"


def test_dependencies_include_ambiguous_method_calls(raw):
    ambiguous = [d for d in raw.dependencies if d["is_ambiguous"]]
    assert ambiguous, "AdventureWorks has XML/hierarchyid method-call rows flagged ambiguous"
    assert all(d["referenced_id"] is None for d in ambiguous)


def test_computed_column_references_function_via_minor_id(raw):
    customer = by_name(raw, "Sales", "Customer")
    fn = by_name(raw, "dbo", "ufnLeadingZeros")
    rows = [
        d
        for d in raw.dependencies
        if d["referencing_id"] == customer["object_id"] and d["referenced_id"] == fn["object_id"]
    ]
    assert rows and rows[0]["referencing_minor_id"] > 0


def test_server_probes(aw_client):
    ex = CatalogExtractor(aw_client)
    info = ex.server_info()
    assert info["product_version"].startswith("16.")
    assert isinstance(info["product_version"], str)
    assert ex.auth_scheme() == "SQL"
    perms = ex.permissions()
    assert perms == {
        "view_server_state": True,
        "view_database_state": True,
        "view_definition": True,
    }
    assert ex.server_start_time() is not None
