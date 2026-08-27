"""Per-scan in-memory lineage graphs and ego-graph traversal.

Edge direction semantics
========================
``object_dependencies`` rows are stored *source USES target*: a view row points at
the tables it selects from, an FK row points from the referencing table to the
referenced table, a trigger row points at its parent table, ``parsed_read`` rows
point from a module to the tables it reads and ``parsed_write`` rows from a module
to the tables it writes.

The API exposes a **data-flow** graph instead, where ``source -> target`` means
"data flows from source to target" (upstream on the left, downstream on the right
in the explorer). Converting a dependency row into a flow edge therefore

* **reverses** ``catalog``, ``fk``, ``synonym`` and ``parsed_read`` rows - the
  table feeds the view, the referenced table feeds the referencing table, the
  base object feeds the synonym, the read table feeds the procedure;
* **keeps** ``parsed_write`` rows (the procedure writes into the table);
* **keeps** ``parsed_exec`` rows (the caller invokes the callee);
* **keeps** ``trigger`` rows (trigger -> parent table).

"Upstream" of a focus = its predecessors in the flow graph (what feeds it);
"downstream" = its successors (what consumes it). Rows without a target
(``ambiguous`` / ``unresolved``) never become edges, nor do self-loops; parallel
rows of the same kind between the same pair collapse into one edge.

Column lineage rows are already stored as data flow (source column -> target
column) and are used as-is. In column mode, nodes are the *objects* owning the
participating columns; procedures/triggers that merely move the data appear only
as ``via`` on the edges (unless they own result-set pseudo columns themselves).

Graphs are loaded once per scan and memoised with ``functools.lru_cache`` (keyed
by the ``Database`` instance and ``scan_id``). Snapshots are immutable, so the
cache only needs clearing when a scan is deleted (``invalidate()``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from sqldoc.store import repo
from sqldoc.store.db import Database

REVERSED_KINDS = frozenset({"catalog", "fk", "synonym", "parsed_read"})
EDGE_KINDS = ("catalog", "fk", "trigger", "synonym", "parsed_read", "parsed_write", "parsed_exec")
CONFIDENCE_RANK = {"unresolved": 0, "inferred": 1, "exact": 2}
_MAX_TEMP_CHAIN = 16


# -- object level ------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphNode:
    id: int
    db: str | None
    schema: str | None
    name: str
    kind: str
    scope: str
    has_lineage_issues: bool = False
    row_count: int | None = None
    exec_count: int | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


@dataclass(frozen=True)
class DepRow:
    """One ``object_dependencies`` row (source USES target)."""

    id: int
    source: int
    target: int | None
    kind: str
    resolution: str = "resolved"
    detail: str | None = None


@dataclass(frozen=True)
class GraphEdge:
    """A data-flow edge: ``source`` feeds ``target``."""

    id: int
    source: int
    target: int
    kind: str
    resolution: str
    detail: str | None


class ScanGraph:
    def __init__(self, nodes: Iterable[GraphNode], deps: Iterable[DepRow]) -> None:
        self.nodes: dict[int, GraphNode] = {n.id: n for n in nodes}
        self.out: dict[int, list[GraphEdge]] = {}
        self.inc: dict[int, list[GraphEdge]] = {}
        seen: set[tuple[int, int, str]] = set()
        for d in deps:
            if d.target is None or d.source not in self.nodes or d.target not in self.nodes:
                continue
            if d.kind in REVERSED_KINDS:
                source, target = d.target, d.source
            else:
                source, target = d.source, d.target
            key = (source, target, d.kind)
            if source == target or key in seen:
                continue
            seen.add(key)
            edge = GraphEdge(d.id, source, target, d.kind, d.resolution, d.detail)
            self.out.setdefault(source, []).append(edge)
            self.inc.setdefault(target, []).append(edge)

    def predecessors(self, node_id: int) -> set[int]:
        return {e.source for e in self.inc.get(node_id, ())}

    def successors(self, node_id: int) -> set[int]:
        return {e.target for e in self.out.get(node_id, ())}

    def degree(self, node_id: int) -> int:
        """Distinct upstream + distinct downstream neighbours."""
        return len(self.predecessors(node_id)) + len(self.successors(node_id))


@dataclass(frozen=True)
class EgoOptions:
    direction: str = "both"  # up | down | both
    depth: int = 2
    kinds: frozenset[str] | None = None
    schemas: frozenset[str] | None = None
    edge_kinds: frozenset[str] | None = None
    include_cascaded: bool = True
    include_external: bool = True
    max_nodes: int = 200


@dataclass
class EgoResult:
    focus: int
    hops: dict[int, int]  # node id -> signed hop (<0 upstream, 0 focus, >0 downstream)
    edges: list[GraphEdge]
    more: dict[int, tuple[int, int]]  # node id -> (upstream, downstream) neighbours not returned
    truncated: bool
    total: int


def _node_filter(opts: EgoOptions) -> Callable[[GraphNode], bool]:
    schemas = {s.casefold() for s in opts.schemas} if opts.schemas is not None else None

    def ok(n: GraphNode) -> bool:
        if opts.kinds is not None and n.kind not in opts.kinds:
            return False
        if schemas is not None and (n.schema or "").casefold() not in schemas:
            return False
        if not opts.include_cascaded and n.scope == "cascaded":
            return False
        return opts.include_external or n.scope != "external"

    return ok


def ego_graph(graph: ScanGraph, focus: int, opts: EgoOptions) -> EgoResult:
    """BFS from ``focus`` up (predecessors) and/or down (successors) with a hop limit.

    Nodes reached upstream are only expanded further upstream (and vice versa), so
    the result is the union of the ancestor and descendant cones. A node reachable
    both ways at the same distance is reported upstream. When the node cap is hit,
    nodes are kept by (hop distance, non-external first, degree, id); because every
    closer hop outranks a farther one, kept nodes always stay connected to the focus.
    """
    if focus not in graph.nodes:
        raise KeyError(focus)
    node_ok = _node_filter(opts)

    def edge_ok(e: GraphEdge) -> bool:
        return opts.edge_kinds is None or e.kind in opts.edge_kinds

    hops: dict[int, int] = {focus: 0}
    up = [focus] if opts.direction in ("up", "both") else []
    down = [focus] if opts.direction in ("down", "both") else []
    for k in range(1, opts.depth + 1):
        next_up: list[int] = []
        next_down: list[int] = []
        for n in up:
            for e in graph.inc.get(n, ()):
                if edge_ok(e) and e.source not in hops and node_ok(graph.nodes[e.source]):
                    hops[e.source] = -k
                    next_up.append(e.source)
        for n in down:
            for e in graph.out.get(n, ()):
                if edge_ok(e) and e.target not in hops and node_ok(graph.nodes[e.target]):
                    hops[e.target] = k
                    next_down.append(e.target)
        up, down = next_up, next_down
        if not up and not down:
            break

    total = len(hops)
    truncated = total > opts.max_nodes
    if truncated:
        ranked = sorted(
            hops,
            key=lambda n: (
                abs(hops[n]),
                graph.nodes[n].scope == "external",
                -graph.degree(n),
                n,
            ),
        )
        keep = set(ranked[: opts.max_nodes]) | {focus}
        hops = {n: h for n, h in hops.items() if n in keep}

    edges = [e for n in hops for e in graph.out.get(n, ()) if e.target in hops and edge_ok(e)]
    more: dict[int, tuple[int, int]] = {}
    for n in hops:
        ups = {
            e.source
            for e in graph.inc.get(n, ())
            if edge_ok(e) and e.source not in hops and node_ok(graph.nodes[e.source])
        }
        downs = {
            e.target
            for e in graph.out.get(n, ())
            if edge_ok(e) and e.target not in hops and node_ok(graph.nodes[e.target])
        }
        more[n] = (len(ups), len(downs))
    return EgoResult(
        focus=focus, hops=hops, edges=edges, more=more, truncated=truncated, total=total
    )


# -- column level ------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnNode:
    id: int
    object_id: int
    name: str
    data_type: str | None
    ordinal: int = 0


@dataclass(frozen=True)
class ColumnEdge:
    """Column data-flow edge; ``id`` is the lineage row id (or ``a+b`` when composed)."""

    id: str
    source: int
    target: int
    confidence: str
    transform: str
    via_object_id: int | None
    expression: str | None
    statement_kind: str | None


class ColumnGraph:
    def __init__(
        self,
        objects: dict[int, GraphNode],
        columns: Iterable[ColumnNode],
        edges: Iterable[ColumnEdge],
        column_totals: dict[int, int],
    ) -> None:
        self.objects = objects
        self.columns: dict[int, ColumnNode] = {c.id: c for c in columns}
        self.column_totals = column_totals
        self.out: dict[int, list[ColumnEdge]] = {}
        self.inc: dict[int, list[ColumnEdge]] = {}
        for e in edges:
            if e.source not in self.columns or e.target not in self.columns:
                continue
            if e.source == e.target:
                continue
            self.out.setdefault(e.source, []).append(e)
            self.inc.setdefault(e.target, []).append(e)
        self._object_columns: dict[int, list[int]] = {}
        for cid in set(self.out) | set(self.inc):
            self._object_columns.setdefault(self.columns[cid].object_id, []).append(cid)
        for lst in self._object_columns.values():
            lst.sort(key=lambda c: (self.columns[c].ordinal, c))
        self._collapsed: ColumnGraph | None = None

    def object_columns(self, object_id: int) -> list[int]:
        """Participating (lineage-bearing) columns of an object, in ordinal order."""
        return list(self._object_columns.get(object_id, ()))

    def find_column(self, object_id: int, name: str) -> ColumnNode | None:
        wanted = name.casefold()
        for cid in self._object_columns.get(object_id, ()):
            if self.columns[cid].name.casefold() == wanted:
                return self.columns[cid]
        return None

    def column_degree(self, object_id: int) -> int:
        return sum(
            len(self.inc.get(c, ())) + len(self.out.get(c, ()))
            for c in self._object_columns.get(object_id, ())
        )

    def collapsed(self) -> ColumnGraph:
        """Compose edges through ``temp_table`` pseudo columns (``collapse_temp``)."""
        if self._collapsed is not None:
            return self._collapsed
        temp = {
            cid
            for cid, c in self.columns.items()
            if c.object_id in self.objects and self.objects[c.object_id].kind == "temp_table"
        }
        if not temp:
            self._collapsed = self
            return self
        edges: list[ColumnEdge] = []
        for lst in self.out.values():
            for e in lst:
                if e.source in temp or e.target in temp:
                    continue
                edges.append(e)
        for lst in self.out.values():
            for first in lst:
                if first.source in temp or first.target not in temp:
                    continue
                edges.extend(self._compose(first))
        objects = {oid: n for oid, n in self.objects.items() if n.kind != "temp_table"}
        columns = [c for cid, c in self.columns.items() if cid not in temp]
        self._collapsed = ColumnGraph(objects, columns, edges, self.column_totals)
        return self._collapsed

    def _compose(self, first: ColumnEdge) -> list[ColumnEdge]:
        temp_kind = "temp_table"
        out: list[ColumnEdge] = []
        stack: list[tuple[list[ColumnEdge], set[int]]] = [([first], {first.source, first.target})]
        while stack:
            path, seen = stack.pop()
            last = path[-1]
            if len(path) > _MAX_TEMP_CHAIN:
                continue
            for nxt in self.out.get(last.target, ()):
                if nxt.target in seen:
                    continue
                target_obj = self.objects.get(self.columns[nxt.target].object_id)
                chain = [*path, nxt]
                if target_obj is not None and target_obj.kind == temp_kind:
                    stack.append((chain, seen | {nxt.target}))
                    continue
                confidence = min(chain, key=lambda e: CONFIDENCE_RANK.get(e.confidence, 0))
                via = next((e.via_object_id for e in reversed(chain) if e.via_object_id), None)
                out.append(
                    ColumnEdge(
                        id="+".join(e.id for e in chain),
                        source=chain[0].source,
                        target=nxt.target,
                        confidence=confidence.confidence,
                        transform="temp",
                        via_object_id=via,
                        expression=nxt.expression,
                        statement_kind=nxt.statement_kind,
                    )
                )
        return out


@dataclass
class ColumnEgoResult:
    focus: int
    hops: dict[int, int]  # object id -> signed hop
    columns: dict[int, list[int]] = field(default_factory=dict)  # object id -> column ids
    edges: list[ColumnEdge] = field(default_factory=list)
    more: dict[int, tuple[int, int]] = field(default_factory=dict)
    truncated: bool = False
    total: int = 0


def column_ego(
    graph: ColumnGraph,
    focus_object: int,
    seeds: Iterable[int],
    *,
    direction: str = "both",
    depth: int = 2,
    min_confidence: str = "unresolved",
    max_nodes: int = 150,
) -> ColumnEgoResult:
    """BFS over column edges from the seed columns, grouped by owning object."""
    min_rank = CONFIDENCE_RANK.get(min_confidence, 0)

    def edge_ok(e: ColumnEdge) -> bool:
        return CONFIDENCE_RANK.get(e.confidence, 0) >= min_rank

    col_hops: dict[int, int] = {c: 0 for c in seeds if c in graph.columns}
    obj_hops: dict[int, int] = {focus_object: 0}
    up = list(col_hops) if direction in ("up", "both") else []
    down = list(col_hops) if direction in ("down", "both") else []
    for k in range(1, depth + 1):
        next_up: list[int] = []
        next_down: list[int] = []
        for c in up:
            for e in graph.inc.get(c, ()):
                if edge_ok(e) and e.source not in col_hops:
                    col_hops[e.source] = -k
                    obj_hops.setdefault(graph.columns[e.source].object_id, -k)
                    next_up.append(e.source)
        for c in down:
            for e in graph.out.get(c, ()):
                if edge_ok(e) and e.target not in col_hops:
                    col_hops[e.target] = k
                    obj_hops.setdefault(graph.columns[e.target].object_id, k)
                    next_down.append(e.target)
        up, down = next_up, next_down
        if not up and not down:
            break

    total = len(obj_hops)
    truncated = total > max_nodes
    if truncated:
        ranked = sorted(
            obj_hops,
            key=lambda o: (
                abs(obj_hops[o]),
                o in graph.objects and graph.objects[o].scope == "external",
                -graph.column_degree(o),
                o,
            ),
        )
        keep = set(ranked[:max_nodes]) | {focus_object}
        obj_hops = {o: h for o, h in obj_hops.items() if o in keep}
        col_hops = {c: h for c, h in col_hops.items() if graph.columns[c].object_id in obj_hops}

    columns: dict[int, list[int]] = {o: [] for o in obj_hops}
    for c in col_hops:
        columns[graph.columns[c].object_id].append(c)
    for lst in columns.values():
        lst.sort(key=lambda c: (graph.columns[c].ordinal, c))
    edges = [
        e for c in col_hops for e in graph.out.get(c, ()) if e.target in col_hops and edge_ok(e)
    ]
    more: dict[int, tuple[int, int]] = {}
    for o, cols in columns.items():
        ups = {
            graph.columns[e.source].object_id
            for c in cols
            for e in graph.inc.get(c, ())
            if edge_ok(e)
        } - set(obj_hops)
        downs = {
            graph.columns[e.target].object_id
            for c in cols
            for e in graph.out.get(c, ())
            if edge_ok(e)
        } - set(obj_hops)
        more[o] = (len(ups), len(downs))
    return ColumnEgoResult(
        focus=focus_object,
        hops=obj_hops,
        columns=columns,
        edges=edges,
        more=more,
        truncated=truncated,
        total=total,
    )


# -- loading -----------------------------------------------------------------------------


@lru_cache(maxsize=16)
def _load_graph_cached(db: Database, scan_id: int) -> ScanGraph:
    with db.session() as s:
        nodes = [GraphNode(**row) for row in repo.graph_nodes(s, scan_id)]
        deps = [DepRow(**row) for row in repo.graph_dependencies(s, scan_id)]
    return ScanGraph(nodes, deps)


@lru_cache(maxsize=16)
def _load_column_graph_cached(db: Database, scan_id: int) -> ColumnGraph:
    objects = load_graph(db, scan_id).nodes
    with db.session() as s:
        columns, edges, totals = repo.column_graph_rows(s, scan_id)
    return ColumnGraph(
        objects,
        [ColumnNode(**c) for c in columns],
        [ColumnEdge(**e) for e in edges],
        totals,
    )


def invalidate() -> None:
    """Drop cached graphs (call after deleting a scan)."""
    _load_graph_cached.cache_clear()
    _load_column_graph_cached.cache_clear()


_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


def _is_terminal(db: Database, scan_id: int) -> bool:
    with db.session() as s:
        scan = repo.get_scan(s, scan_id)
    return scan is not None and scan.status in _TERMINAL


def load_graph(db: Database, scan_id: int) -> ScanGraph:
    """Object graph for a scan; memoised only once the scan can no longer change."""
    if _is_terminal(db, scan_id):
        return _load_graph_cached(db, scan_id)
    return _load_graph_cached.__wrapped__(db, scan_id)


def load_column_graph(db: Database, scan_id: int) -> ColumnGraph:
    """Column graph for a scan; memoised only once the scan can no longer change."""
    if _is_terminal(db, scan_id):
        return _load_column_graph_cached(db, scan_id)
    return _load_column_graph_cached.__wrapped__(db, scan_id)
