"""Compute the scan closure: selected-schema objects plus everything they reach.

Pure function over pre-fetched catalog rows so it is unit-testable without a
server. Only *outgoing* references are followed (what in-scope objects use);
objects that merely reference in-scope objects are not pulled in.

Dependency rows are interpreted in this order (see the design spec):
1. ``referenced_id`` set              -> resolved same-database object
2. ``is_ambiguous``                    -> noise (XML/hierarchyid methods, aliases);
                                          edge only, never a node
3. linked server (not our own name)    -> external
4. ``referenced_database_name`` set    -> cascade if configured on this connection, else external
5. ``is_caller_dependent``             -> try ``dbo`` in the same database
6. ``inserted`` / ``deleted``          -> ignored (trigger pseudo tables)
7. anything else                        -> unresolved (temp tables, dropped objects)
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqldoc.config.schema import ConnectionCfg, ScanOptions
from sqldoc.mssql.identity import external_key, parse_multipart_name

ObjId = tuple[str, int]  # (database name as enumerated, sys.objects.object_id)

IN_SCOPE = "in_scope"
CASCADED = "cascaded"


@dataclass(frozen=True)
class CatalogObject:
    db: str
    object_id: int
    schema: str
    name: str
    kind: str
    parent_object_id: int | None = None

    @property
    def id(self) -> ObjId:
        return (self.db, self.object_id)


@dataclass(frozen=True)
class DependencyRow:
    db: str
    referencing_id: int
    referencing_minor_id: int
    referenced_id: int | None
    referenced_server_name: str | None
    referenced_database_name: str | None
    referenced_schema_name: str | None
    referenced_entity_name: str
    is_caller_dependent: bool
    is_ambiguous: bool
    is_schema_bound: bool = False


@dataclass(frozen=True)
class ForeignKeyRow:
    db: str
    fk_id: int
    parent_object_id: int
    referenced_object_id: int


@dataclass(frozen=True)
class TriggerRow:
    db: str
    object_id: int
    parent_id: int


@dataclass(frozen=True)
class SynonymRow:
    db: str
    object_id: int
    base_object_name: str


@dataclass(frozen=True)
class ExternalRef:
    server: str | None
    database: str | None
    schema: str | None
    name: str

    @property
    def key(self) -> str:
        return external_key(self.server, self.database, self.schema, self.name)


@dataclass(frozen=True)
class Edge:
    source: ObjId
    target: ObjId | None
    kind: str  # catalog | fk | trigger | synonym
    resolution: str = "resolved"  # resolved | caller_dependent | ambiguous | external | unresolved
    is_ambiguous: bool = False
    is_caller_dependent: bool = False
    is_schema_bound: bool = False
    referencing_minor_id: int = 0
    referenced_name: str | None = None
    external_key: str | None = None
    fk_id: int | None = None


@dataclass
class Closure:
    scope: dict[ObjId, str] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    externals: dict[str, ExternalRef] = field(default_factory=dict)


class Universe:
    """Every enumerated object across the connection's configured databases."""

    def __init__(self, objects: Iterable[CatalogObject]) -> None:
        self.by_id: dict[ObjId, CatalogObject] = {}
        self._by_name: dict[tuple[str, str, str], CatalogObject] = {}
        for o in objects:
            self.by_id[o.id] = o
            self._by_name[(o.db.casefold(), o.schema.casefold(), o.name.casefold())] = o

    def get(self, db: str, object_id: int) -> CatalogObject | None:
        return self.by_id.get((db, object_id))

    def find(self, db: str, schema: str, name: str) -> CatalogObject | None:
        return self._by_name.get((db.casefold(), schema.casefold(), name.casefold()))

    def __iter__(self):
        return iter(self.by_id.values())


# --- resolution outcomes -------------------------------------------------------------


@dataclass(frozen=True)
class _Resolved:
    target: CatalogObject
    resolution: str = "resolved"


@dataclass(frozen=True)
class _External:
    ref: ExternalRef


class _Ignored:
    pass


@dataclass(frozen=True)
class _Unresolved:
    name: str
    resolution: str = "unresolved"


def _resolve_name(
    universe: Universe,
    conn: ConnectionCfg,
    server_name: str | None,
    current_db: str,
    *,
    server: str | None,
    database: str | None,
    schema: str | None,
    name: str,
) -> _Resolved | _External | _Unresolved:
    if server and server.casefold() != (server_name or "").casefold():
        return _External(ExternalRef(server, database, schema, name))
    if database:
        if not conn.is_configured_database(database):
            return _External(ExternalRef(None, database, schema, name))
        target = universe.find(database, schema or "dbo", name)
        return _Resolved(target) if target else _Unresolved(_display(database, schema, name))
    target = universe.find(current_db, schema or "dbo", name)
    return _Resolved(target) if target else _Unresolved(_display(None, schema, name))


def _display(database: str | None, schema: str | None, name: str) -> str:
    return ".".join(p for p in (database, schema, name) if p)


def _resolve_dependency(
    universe: Universe,
    conn: ConnectionCfg,
    server_name: str | None,
    obj: CatalogObject,
    dep: DependencyRow,
) -> _Resolved | _External | _Ignored | _Unresolved:
    entity = dep.referenced_entity_name
    if dep.referenced_id is not None:
        target = universe.get(obj.db, dep.referenced_id)
        if target is not None:
            return _Resolved(target)
        return _Unresolved(_display(None, dep.referenced_schema_name, entity))
    if dep.is_ambiguous:
        return _Unresolved(_display(None, dep.referenced_schema_name, entity), "ambiguous")
    if (
        obj.kind == "trigger"
        and not dep.referenced_schema_name
        and entity.casefold() in ("inserted", "deleted")
    ):
        return _Ignored()
    if dep.is_caller_dependent and not dep.referenced_database_name:
        target = universe.find(obj.db, "dbo", entity)
        if target is not None:
            return _Resolved(target, "caller_dependent")
        return _Unresolved(entity)
    return _resolve_name(
        universe,
        conn,
        server_name,
        obj.db,
        server=dep.referenced_server_name,
        database=dep.referenced_database_name,
        schema=dep.referenced_schema_name,
        name=entity,
    )


# --- closure -------------------------------------------------------------------------


def compute_closure(
    universe: Universe,
    deps: Iterable[DependencyRow],
    fks: Iterable[ForeignKeyRow],
    triggers: Iterable[TriggerRow],
    synonyms: Iterable[SynonymRow],
    conn: ConnectionCfg,
    options: ScanOptions,
    server_name: str | None = None,
) -> Closure:
    deps_by_obj: dict[ObjId, list[DependencyRow]] = {}
    for d in deps:
        deps_by_obj.setdefault((d.db, d.referencing_id), []).append(d)
    fks_by_obj: dict[ObjId, list[ForeignKeyRow]] = {}
    for fk in fks:
        fks_by_obj.setdefault((fk.db, fk.parent_object_id), []).append(fk)
    triggers_by_table: dict[ObjId, list[TriggerRow]] = {}
    for tr in triggers:
        triggers_by_table.setdefault((tr.db, tr.parent_id), []).append(tr)
    synonyms_by_obj: dict[ObjId, SynonymRow] = {(s.db, s.object_id): s for s in synonyms}

    closure = Closure()
    seen_edges: set[tuple] = set()
    work: deque[ObjId] = deque()
    visited: set[ObjId] = set()

    def add_edge(edge: Edge) -> None:
        key = (
            edge.source,
            edge.target,
            edge.kind,
            edge.referencing_minor_id,
            edge.external_key,
            edge.referenced_name,
            edge.fk_id,
        )
        if key not in seen_edges:
            seen_edges.add(key)
            closure.edges.append(edge)

    def enqueue(target: ObjId) -> None:
        closure.scope.setdefault(target, CASCADED)
        if target not in visited:
            work.append(target)

    for obj in universe:
        if conn.is_selected(obj.db, obj.schema):
            closure.scope[obj.id] = IN_SCOPE
            work.append(obj.id)

    while work:
        oid = work.popleft()
        if oid in visited:
            continue
        visited.add(oid)
        obj = universe.by_id[oid]

        for dep in deps_by_obj.get(oid, ()):
            outcome = _resolve_dependency(universe, conn, server_name, obj, dep)
            common = dict(
                source=oid,
                kind="catalog",
                is_ambiguous=dep.is_ambiguous,
                is_caller_dependent=dep.is_caller_dependent,
                is_schema_bound=dep.is_schema_bound,
                referencing_minor_id=dep.referencing_minor_id,
            )
            match outcome:
                case _Resolved(target, resolution):
                    if target.id == oid:
                        continue  # computed columns referencing their own table
                    add_edge(
                        Edge(
                            target=target.id,
                            resolution=resolution,
                            referenced_name=dep.referenced_entity_name,
                            **common,
                        )
                    )
                    enqueue(target.id)
                case _External(ref):
                    closure.externals[ref.key] = ref
                    add_edge(
                        Edge(
                            target=None,
                            resolution="external",
                            external_key=ref.key,
                            referenced_name=ref.name,
                            **common,
                        )
                    )
                case _Unresolved(name, resolution):
                    add_edge(
                        Edge(target=None, resolution=resolution, referenced_name=name, **common)
                    )
                case _Ignored():
                    pass

        if obj.kind == "table":
            if options.cascade_foreign_keys:
                for fk in fks_by_obj.get(oid, ()):
                    target = (obj.db, fk.referenced_object_id)
                    if target in universe.by_id:
                        add_edge(Edge(source=oid, target=target, kind="fk", fk_id=fk.fk_id))
                        enqueue(target)
            if closure.scope.get(oid) == IN_SCOPE or options.include_triggers_of_cascaded_tables:
                for tr in triggers_by_table.get(oid, ()):
                    trigger_id = (obj.db, tr.object_id)
                    if trigger_id in universe.by_id:
                        add_edge(Edge(source=trigger_id, target=oid, kind="trigger"))
                        enqueue(trigger_id)

        if obj.kind == "trigger" and obj.parent_object_id is not None:
            parent = (obj.db, obj.parent_object_id)
            if parent in universe.by_id:
                add_edge(Edge(source=oid, target=parent, kind="trigger"))
                enqueue(parent)

        if obj.kind == "synonym" and oid in synonyms_by_obj:
            ref = parse_multipart_name(synonyms_by_obj[oid].base_object_name)
            outcome = _resolve_name(
                universe,
                conn,
                server_name,
                obj.db,
                server=ref.server,
                database=ref.database,
                schema=ref.schema,
                name=ref.name,
            )
            match outcome:
                case _Resolved(target, resolution):
                    add_edge(
                        Edge(
                            source=oid,
                            target=target.id,
                            kind="synonym",
                            resolution=resolution,
                            referenced_name=ref.display(),
                        )
                    )
                    enqueue(target.id)
                case _External(ext):
                    closure.externals[ext.key] = ext
                    add_edge(
                        Edge(
                            source=oid,
                            target=None,
                            kind="synonym",
                            resolution="external",
                            external_key=ext.key,
                            referenced_name=ref.display(),
                        )
                    )
                case _Unresolved(name, resolution):
                    add_edge(
                        Edge(
                            source=oid,
                            target=None,
                            kind="synonym",
                            resolution=resolution,
                            referenced_name=name,
                        )
                    )

    return closure
