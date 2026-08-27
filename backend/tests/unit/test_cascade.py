"""Scope + cascade closure over an in-memory catalog."""

from sqldoc.config.schema import AuthCfg, ConnectionCfg, DatabaseCfg, ScanOptions
from sqldoc.scope.cascade import compute_closure
from tests.fixtures.fake_catalog import FakeCatalog


def cfg(*dbs: tuple[str, list[str]]) -> ConnectionCfg:
    return ConnectionCfg(
        name="c",
        host="h",
        auth=AuthCfg(mode="integrated"),
        databases=[DatabaseCfg(name=n, schemas=s) for n, s in dbs],
    )


def run(cat: FakeCatalog, conn: ConnectionCfg, **opts):
    return compute_closure(
        cat.universe(),
        cat.deps,
        cat.fks,
        cat.triggers,
        cat.synonyms,
        conn,
        ScanOptions(**opts),
        server_name="THISSERVER",
    )


def test_seed_is_selected_schemas_only():
    cat = FakeCatalog()
    t1 = cat.table("AW", "Sales", "Customer")
    cat.table("AW", "Person", "Person")
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert closure.scope == {("AW", t1): "in_scope"}
    assert closure.edges == []


def test_transitive_cascade_through_views_and_computed_columns():
    cat = FakeCatalog()
    v = cat.view("AW", "Sales", "vCustomer")
    person = cat.table("AW", "Person", "Person")
    fn = cat.function("AW", "dbo", "ufnLeadingZeros")
    cat.resolved_dep("AW", v, person)
    cat.resolved_dep("AW", person, fn, minor_id=3)  # computed column on Person uses fn
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert closure.scope == {
        ("AW", v): "in_scope",
        ("AW", person): "cascaded",
        ("AW", fn): "cascaded",
    }
    kinds = {
        (e.source, e.target): (e.kind, e.resolution, e.referencing_minor_id) for e in closure.edges
    }
    assert kinds[(("AW", v), ("AW", person))] == ("catalog", "resolved", 0)
    assert kinds[(("AW", person), ("AW", fn))] == ("catalog", "resolved", 3)


def test_cycles_terminate():
    cat = FakeCatalog()
    a = cat.proc("AW", "Sales", "A")
    b = cat.proc("AW", "Person", "B")
    cat.resolved_dep("AW", a, b)
    cat.resolved_dep("AW", b, a)
    t = cat.table("AW", "Sales", "Tree")
    cat.fk("AW", t, t)
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert closure.scope[("AW", b)] == "cascaded"
    assert sum(1 for e in closure.edges if e.kind == "fk") == 1


def test_foreign_keys_cascade_by_default_and_can_be_disabled():
    cat = FakeCatalog()
    detail = cat.table("AW", "Sales", "SalesOrderDetail")
    product = cat.table("AW", "Production", "Product")
    cat.fk("AW", detail, product)
    on = run(cat, cfg(("AW", ["Sales"])))
    assert on.scope[("AW", product)] == "cascaded"
    assert any(e.kind == "fk" and e.target == ("AW", product) for e in on.edges)
    off = run(cat, cfg(("AW", ["Sales"])), cascade_foreign_keys=False)
    assert ("AW", product) not in off.scope
    assert off.edges == []


def test_only_outgoing_references_are_followed():
    cat = FakeCatalog()
    t = cat.table("AW", "Sales", "Customer")
    outsider = cat.view("AW", "Reporting", "vCustomers")
    cat.resolved_dep("AW", outsider, t)  # outsider reads the in-scope table
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert ("AW", outsider) not in closure.scope


def test_triggers_follow_their_tables():
    cat = FakeCatalog()
    t_in = cat.table("AW", "Sales", "SalesOrderDetail")
    tr_in = cat.trigger("AW", "Sales", "iduSalesOrderDetail", parent=t_in)
    log = cat.proc("AW", "dbo", "uspLogError")
    cat.resolved_dep("AW", tr_in, log)
    t_casc = cat.table("AW", "Person", "Person")
    tr_casc = cat.trigger("AW", "Person", "iuPerson", parent=t_casc)
    cat.fk("AW", t_in, t_casc)

    closure = run(cat, cfg(("AW", ["Sales"])))
    assert closure.scope[("AW", tr_in)] == "in_scope"
    assert closure.scope[("AW", log)] == "cascaded"
    assert closure.scope[("AW", tr_casc)] == "cascaded"
    trigger_edges = [e for e in closure.edges if e.kind == "trigger"]
    assert (("AW", tr_in), ("AW", t_in)) in {(e.source, e.target) for e in trigger_edges}

    without = run(cat, cfg(("AW", ["Sales"])), include_triggers_of_cascaded_tables=False)
    assert ("AW", tr_casc) not in without.scope
    assert closure.scope[("AW", tr_in)] == "in_scope"


def test_cross_database_reference_into_configured_database_cascades():
    cat = FakeCatalog()
    v = cat.view("AW", "Sales", "vRemote")
    remote = cat.table("Staging", "etl", "Loads")
    cat.dep("AW", v, entity="Loads", schema="etl", database="Staging")
    closure = run(cat, cfg(("AW", ["Sales"]), ("Staging", ["dbo"])))
    assert closure.scope[("Staging", remote)] == "cascaded"
    assert closure.externals == {}


def test_cross_database_reference_defaults_schema_to_dbo():
    cat = FakeCatalog()
    v = cat.view("AW", "Sales", "vRemote")
    remote = cat.table("Staging", "dbo", "Loads")
    cat.dep("AW", v, entity="Loads", schema=None, database="Staging")
    closure = run(cat, cfg(("AW", ["Sales"]), ("Staging", ["etl"])))
    assert closure.scope[("Staging", remote)] == "cascaded"


def test_reference_to_unconfigured_database_is_external():
    cat = FakeCatalog()
    v = cat.view("AW", "Sales", "vRemote")
    cat.dep("AW", v, entity="Loads", schema="etl", database="Other")
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert list(closure.externals) == ["external||Other|etl|Loads"]
    edge = closure.edges[0]
    assert edge.target is None and edge.resolution == "external"
    assert edge.external_key == "external||Other|etl|Loads"


def test_linked_server_reference_is_external_but_own_server_name_is_not():
    cat = FakeCatalog()
    v = cat.view("AW", "Sales", "vRemote")
    local = cat.table("AW", "dbo", "Local")
    cat.dep("AW", v, entity="T", schema="dbo", database="Other", server="LINKED")
    cat.dep("AW", v, entity="Local", schema="dbo", database="AW", server="thisserver")
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert list(closure.externals) == ["external|LINKED|Other|dbo|T"]
    assert closure.scope[("AW", local)] == "cascaded"


def test_ambiguous_rows_never_create_nodes():
    cat = FakeCatalog()
    v = cat.view("AW", "Sales", "vPersonDemographics")
    cat.dep("AW", v, entity="value", schema="Demographics", database="ref", ambiguous=True)
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert closure.externals == {}
    assert closure.scope == {("AW", v): "in_scope"}
    assert [e.resolution for e in closure.edges] == ["ambiguous"]
    assert closure.edges[0].target is None


def test_caller_dependent_resolves_to_dbo_or_is_unresolved():
    cat = FakeCatalog()
    p = cat.proc("AW", "Sales", "P")
    helper = cat.proc("AW", "dbo", "Helper")
    cat.dep("AW", p, entity="Helper", caller_dependent=True)
    cat.dep("AW", p, entity="Ghost", caller_dependent=True)
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert closure.scope[("AW", helper)] == "cascaded"
    by_name = {e.referenced_name: e for e in closure.edges}
    assert by_name["Helper"].resolution == "caller_dependent"
    assert by_name["Ghost"].resolution == "unresolved" and by_name["Ghost"].target is None


def test_inserted_deleted_pseudo_tables_are_ignored():
    cat = FakeCatalog()
    t = cat.table("AW", "Sales", "T")
    tr = cat.trigger("AW", "Sales", "trT", parent=t)
    cat.dep("AW", tr, entity="inserted")
    cat.dep("AW", tr, entity="deleted")
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert [e for e in closure.edges if e.kind == "catalog"] == []


def test_synonym_chain_cascades_to_base_object():
    cat = FakeCatalog()
    syn = cat.synonym("AW", "Sales", "PersonSyn", base="[Person].[Person]")
    person = cat.table("AW", "Person", "Person")
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert closure.scope[("AW", person)] == "cascaded"
    assert any(
        e.kind == "synonym" and e.source == ("AW", syn) and e.target == ("AW", person)
        for e in closure.edges
    )


def test_name_resolution_is_case_insensitive():
    cat = FakeCatalog()
    v = cat.view("AW", "Sales", "V")
    t = cat.table("AW", "Person", "Address")
    cat.dep("AW", v, entity="ADDRESS", schema="person")
    closure = run(cat, cfg(("aw", ["SALES"])))
    assert closure.scope[("AW", t)] == "cascaded"


def test_self_references_do_not_create_edges():
    """Computed columns referencing their own table show up as self-dependency rows."""
    cat = FakeCatalog()
    t = cat.table("AW", "Sales", "SalesOrderHeader")
    cat.resolved_dep("AW", t, t, minor_id=5)
    closure = run(cat, cfg(("AW", ["Sales"])))
    assert closure.scope == {("AW", t): "in_scope"}
    assert closure.edges == []
