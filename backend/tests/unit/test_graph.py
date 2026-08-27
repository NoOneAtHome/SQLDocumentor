"""graph/traverse: dependency-row -> data-flow conversion, ego BFS, caps, column mode."""

import pytest

from sqldoc.graph.traverse import (
    ColumnEdge,
    ColumnGraph,
    ColumnNode,
    DepRow,
    EgoOptions,
    GraphNode,
    ScanGraph,
    column_ego,
    ego_graph,
    load_column_graph,
    load_graph,
)
from tests.unit import test_api_support as support

seeded = support.seeded


def node(id_, name, kind="table", scope="in_scope", schema="Sales", **kw):
    return GraphNode(
        id=id_,
        db="AW",
        schema=schema,
        name=name,
        kind=kind,
        scope=scope,
        has_lineage_issues=kw.get("issues", False),
        row_count=kw.get("rows"),
        exec_count=kw.get("execs"),
    )


@pytest.fixture
def graph() -> ScanGraph:
    nodes = [
        node(1, "Customer"),
        node(2, "vCustomer", "view"),
        node(3, "Person", scope="cascaded", schema="Person"),
        node(4, "Address", scope="cascaded", schema="Person"),
        node(5, "uspUpdate", "procedure"),
        node(6, "trCustomer", "trigger"),
        node(7, "Remote", "external", scope="external", schema="dbo"),
    ]
    deps = [
        DepRow(1, 2, 1, "catalog"),  # view uses Customer
        DepRow(2, 2, 3, "catalog"),  # view uses Person
        DepRow(3, 1, 3, "fk", detail="FK_Customer_Person"),  # Customer -> Person
        DepRow(4, 3, 4, "fk"),  # Person -> Address
        DepRow(5, 6, 1, "trigger"),  # trigger on Customer
        DepRow(6, 5, 3, "parsed_read"),  # proc reads Person
        DepRow(7, 5, 1, "parsed_write"),  # proc writes Customer
        DepRow(8, 6, 5, "parsed_exec"),  # trigger executes proc
        DepRow(9, 5, 7, "catalog", "external"),  # proc references external
        DepRow(10, 5, None, "catalog", "ambiguous"),  # never an edge
        DepRow(11, 2, 1, "catalog"),  # duplicate pair/kind -> deduped
        DepRow(12, 5, 5, "parsed_exec"),  # self loop -> dropped
    ]
    return ScanGraph(nodes, deps)


def flow(graph: ScanGraph) -> set[tuple[int, int, str]]:
    return {(e.source, e.target, e.kind) for edges in graph.out.values() for e in edges}


def test_dependency_rows_become_data_flow_edges(graph):
    assert flow(graph) == {
        (1, 2, "catalog"),  # reversed: table feeds view
        (3, 2, "catalog"),
        (3, 1, "fk"),  # reversed: referenced table feeds referencing table
        (4, 3, "fk"),
        (6, 1, "trigger"),  # kept: trigger -> parent table
        (3, 5, "parsed_read"),  # reversed: read table feeds proc
        (5, 1, "parsed_write"),  # kept: proc writes table
        (6, 5, "parsed_exec"),  # kept: caller -> callee
        (7, 5, "catalog"),  # reversed: external feeds proc
    }
    fk_edge = next(e for e in graph.out[3] if e.kind == "fk")
    assert fk_edge.detail == "FK_Customer_Person" and fk_edge.id == 3
    assert {e.source for e in graph.inc[5]} == {3, 6, 7}


def test_upstream_bfs_assigns_negative_hops(graph):
    res = ego_graph(graph, 2, EgoOptions(direction="up", depth=2))
    assert res.hops == {2: 0, 1: -1, 3: -1, 6: -2, 5: -2, 4: -2}
    assert res.total == 6 and not res.truncated
    assert {(e.source, e.target) for e in res.edges} == {
        (1, 2),
        (3, 2),
        (3, 1),
        (4, 3),
        (6, 1),
        (5, 1),
        (3, 5),
        (6, 5),
    }
    assert res.more[5] == (1, 0)  # external node 7 not returned upstream of proc


def test_downstream_bfs_assigns_positive_hops(graph):
    res = ego_graph(graph, 3, EgoOptions(direction="down", depth=1))
    assert res.hops == {3: 0, 2: 1, 1: 1, 5: 1}
    deeper = ego_graph(graph, 3, EgoOptions(direction="down", depth=3))
    assert deeper.hops == res.hops  # nothing new beyond one hop


def test_both_directions_and_ties_go_upstream(graph):
    res = ego_graph(graph, 1, EgoOptions(direction="both", depth=1))
    assert res.hops == {1: 0, 3: -1, 6: -1, 5: -1, 2: 1}


def test_more_counts_neighbours_not_returned(graph):
    res = ego_graph(graph, 2, EgoOptions(direction="up", depth=1))
    assert res.hops == {2: 0, 1: -1, 3: -1}
    assert res.more[2] == (0, 0)
    assert res.more[1] == (2, 0)  # up: trigger + proc ; down: view is included
    assert res.more[3] == (1, 1)  # up: Address ; down: proc


def test_node_and_edge_filters(graph):
    up2 = EgoOptions(direction="up", depth=2)
    no_ext = ego_graph(graph, 5, EgoOptions(direction="up", depth=1, include_external=False))
    assert set(no_ext.hops) == {5, 3, 6}
    tables = ego_graph(graph, 2, EgoOptions(**{**up2.__dict__, "kinds": frozenset({"table"})}))
    assert set(tables.hops) == {2, 1, 3, 4}
    sales = ego_graph(graph, 2, EgoOptions(**{**up2.__dict__, "schemas": frozenset({"sales"})}))
    assert set(sales.hops) == {2, 1, 6, 5}
    fk_only = ego_graph(graph, 1, EgoOptions(**{**up2.__dict__, "edge_kinds": frozenset({"fk"})}))
    assert set(fk_only.hops) == {1, 3, 4}
    assert all(e.kind == "fk" for e in fk_only.edges)
    no_cascaded = ego_graph(graph, 2, EgoOptions(**{**up2.__dict__, "include_cascaded": False}))
    assert set(no_cascaded.hops) == {2, 1, 6, 5}


def test_cap_prefers_close_then_non_external_then_high_degree(graph):
    res = ego_graph(graph, 2, EgoOptions(direction="up", depth=2, max_nodes=3))
    assert set(res.hops) == {2, 1, 3} and res.truncated and res.total == 6
    res4 = ego_graph(graph, 2, EgoOptions(direction="up", depth=2, max_nodes=4))
    assert set(res4.hops) == {2, 1, 3, 5}  # proc has the highest degree at hop 2
    ext = ego_graph(graph, 5, EgoOptions(direction="up", depth=1, max_nodes=3))
    assert set(ext.hops) == {5, 3, 6} and ext.truncated and ext.total == 4
    assert ext.more[5] == (1, 1)  # Remote hidden upstream; Customer not in an up-only result


def test_unknown_focus_raises(graph):
    with pytest.raises(KeyError):
        ego_graph(graph, 999, EgoOptions())


# -- column graph ----------------------------------------------------------------------


def ce(id_, source, target, confidence, transform, via=None):
    return ColumnEdge(
        id=id_,
        source=source,
        target=target,
        confidence=confidence,
        transform=transform,
        via_object_id=via,
        expression=None,
        statement_kind=None,
    )


@pytest.fixture
def column_graph() -> ColumnGraph:
    objects = {
        1: node(1, "Customer"),
        2: node(2, "vCustomer", "view"),
        3: node(3, "Person", schema="Person"),
        9: node(9, "#tmp", "temp_table"),
        5: node(5, "usp", "procedure"),
    }
    columns = [
        ColumnNode(11, 1, "CustomerID", "int"),
        ColumnNode(13, 1, "AccountNumber", "varchar(10)"),
        ColumnNode(21, 2, "CustomerID", "int"),
        ColumnNode(22, 2, "FirstName", "nvarchar(50)"),
        ColumnNode(32, 3, "FirstName", "nvarchar(50)"),
        ColumnNode(91, 9, "FirstName", None),
    ]
    edges = [
        ce("1", 32, 22, "exact", "passthrough"),
        ce("2", 11, 21, "exact", "passthrough"),
        ce("3", 32, 91, "exact", "temp", via=5),
        ce("4", 91, 13, "inferred", "expression", via=5),
        ce("5", 11, 13, "inferred", "computed"),
    ]
    return ColumnGraph(objects, columns, edges, {1: 4, 2: 2, 3: 3, 9: 1, 5: 0})


def test_column_seeds_default_to_lineage_bearing_columns(column_graph):
    assert column_graph.object_columns(2) == [21, 22]
    res = column_ego(column_graph, 2, [21, 22], direction="up", depth=1)
    assert res.hops == {2: 0, 3: -1, 1: -1}
    assert res.columns == {2: [21, 22], 3: [32], 1: [11]}
    assert {e.id for e in res.edges} == {"1", "2"}
    single = column_ego(column_graph, 2, [22], direction="up", depth=1)
    assert set(single.hops) == {2, 3}


def test_column_downstream_through_temp_and_collapse(column_graph):
    res = column_ego(column_graph, 3, [32], direction="down", depth=2)
    assert res.hops == {3: 0, 2: 1, 9: 1, 1: 2}
    collapsed = column_graph.collapsed()
    assert 9 not in collapsed.objects and 91 not in collapsed.columns
    res2 = column_ego(collapsed, 3, [32], direction="down", depth=2)
    assert res2.hops == {3: 0, 2: 1, 1: 1}
    composed = next(e for e in res2.edges if e.target == 13)
    assert composed.source == 32 and composed.confidence == "inferred"
    assert composed.via_object_id == 5 and composed.id == "3+4"


def test_column_min_confidence_and_cap(column_graph):
    exact = column_ego(column_graph, 3, [32], direction="down", depth=2, min_confidence="exact")
    assert set(exact.hops) == {3, 2, 9}
    capped = column_ego(column_graph, 3, [32], direction="down", depth=2, max_nodes=2)
    assert capped.truncated and capped.total == 4 and len(capped.hops) == 2
    assert 3 in capped.hops
    assert capped.more[3][1] >= 1


# -- loading from the store ------------------------------------------------------------


def test_load_graph_from_snapshot_is_cached(seeded):
    db, seed = seeded.runtime.db, seeded.seed
    g = load_graph(db, seed.scan_id)
    assert g is load_graph(db, seed.scan_id)
    ids = seed.ids
    assert (ids["customer"], ids["view"], "catalog") in flow(g)
    assert (ids["proc"], ids["customer"], "parsed_write") in flow(g)
    assert (ids["person"], ids["customer"], "fk") in flow(g)
    assert (ids["remote"], ids["proc"], "catalog") in flow(g)
    fk_edge = next(e for e in g.out[ids["person"]] if e.kind == "fk")
    assert fk_edge.detail == "FK_Customer_Person_PersonID"
    assert g.nodes[ids["customer"]].row_count == 19820
    assert g.nodes[ids["proc"]].exec_count == 42 and g.nodes[ids["proc"]].has_lineage_issues
    cg = load_column_graph(db, seed.scan_id)
    assert cg.object_columns(ids["view"]) == [
        seed.cols[("view", "CustomerID")],
        seed.cols[("view", "FirstName")],
    ]
    assert cg.column_totals[ids["customer"]] == 4
