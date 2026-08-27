"""Column-level lineage over sqlglot: qualify -> lineage() -> classified edges.

One object is analyzed at a time, one level deep: a view's edges end at the
columns of whatever it selects from (table *or* view). Multi-hop lineage is
assembled later by walking stored edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlglot import exp, parse_one
from sqlglot.errors import ErrorLevel, OptimizeError, ParseError, SqlglotError
from sqlglot.lineage import Node, lineage
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import build_scope

from sqldoc.lineage import rewrite
from sqldoc.lineage.schema_builder import (
    TABLEVAR_SCHEMA,
    TEMP_SCHEMA,
    LineageCatalog,
    TableKey,
)
from sqldoc.lineage.splitter import Statement, module_body, split_statements, view_query
from sqldoc.lineage.symbols import SymbolTable

EXACT, INFERRED, UNRESOLVED = "exact", "inferred", "unresolved"
MAX_EXPRESSION_SQL = 2000


@dataclass(frozen=True)
class ColumnEdge:
    target_column: str
    target_index: int | None
    source_table: TableKey | None
    source_name: str | None  # display name when the source could not be resolved
    source_column: str | None
    confidence: str
    transform: str  # passthrough | expression | aggregate | star | temp | pseudo | computed
    expression_sql: str
    statement_index: int
    statement_kind: str
    via: str | None = None
    target_kind: str = "self"  # self | table | temp | tablevar | resultset
    target_table: TableKey | None = None
    target_name: str | None = None  # display when the target could not be resolved
    resultset_index: int | None = None


@dataclass(frozen=True)
class ObjectRefEdge:
    kind: str  # read | write | exec | function
    table: TableKey | None
    name: str
    schema: str | None
    statement_index: int
    database: str | None = None

    def display(self) -> str:
        if self.table is not None:
            return self.table.display()
        return ".".join(p for p in (self.database, self.schema, self.name) if p)


@dataclass(frozen=True)
class Issue:
    kind: str
    message: str
    statement_index: int | None = None
    snippet: str | None = None


@dataclass
class LineageResult:
    column_edges: list[ColumnEdge] = field(default_factory=list)
    object_refs: list[ObjectRefEdge] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    has_dynamic_sql: bool = False
    resultsets: list[list[str]] = field(default_factory=list)
    status: str = "ok"  # ok | partial | failed

    def finalize(self) -> LineageResult:
        if self.status != "failed":
            self.status = "partial" if self.issues else "ok"
        return self


# --- per-query analysis -----------------------------------------------------------------


@dataclass(frozen=True)
class SourceHit:
    table: TableKey | None
    name: str | None
    column: str | None
    exact_path: bool
    transform: str


@dataclass
class OutputColumn:
    index: int
    name: str
    expression_sql: str
    hits: list[SourceHit]


@dataclass
class QueryLineage:
    outputs: list[OutputColumn]
    reads: list[ObjectRefEdge]
    functions: list[ObjectRefEdge]
    issues: list[Issue]
    is_assignment: bool = False


class QueryAnalyzer:
    def __init__(self, catalog: LineageCatalog, database: str) -> None:
        self.catalog = catalog
        self.database = database
        self._schema = None
        self._names = _OriginalNames(exp.Select())

    @property
    def schema(self):
        if self._schema is None:
            self._schema = self.catalog.mapping_schema()
        return self._schema

    def invalidate(self) -> None:
        self._schema = None

    def register_pseudo(self, key: TableKey, columns: list[str]) -> None:
        """Make a freshly registered pseudo relation visible to qualification."""
        if self._schema is None:
            return
        try:
            self._schema.add_table(
                exp.table_(key.name, db=key.schema, catalog=key.db),
                {c: "unknown" for c in columns},
                dialect="tsql",
            )
        except Exception:  # noqa: BLE001 - fall back to a rebuild
            self._schema = None

    def analyze(self, query: exp.Expression, statement_index: int) -> QueryLineage:
        issues: list[Issue] = []
        query = query.copy()
        self._names = _OriginalNames(query)
        _rename_pseudo_tables(query)
        original = query.copy()
        is_assignment = _rewrite_assignments(query)
        _alias_unnamed(query)
        try:
            qualified = qualify(
                query,
                dialect="tsql",
                schema=self.schema,
                catalog=self.database,
                db="dbo",
                validate_qualify_columns=False,
                allow_partial_qualification=True,
                identify=False,
            )
        except (OptimizeError, SqlglotError, RecursionError) as exc:
            issues.append(Issue("qualify_failed", str(exc)[:500], statement_index))
            reads = self._reads(original, statement_index)
            return QueryLineage([], reads, [], issues, is_assignment)

        try:
            scope = build_scope(qualified)
            nodes = lineage(None, qualified, schema=self.schema, dialect="tsql", scope=scope)
        except (SqlglotError, RecursionError, Exception) as exc:  # noqa: BLE001 - third-party
            issues.append(Issue("lineage_failed", str(exc)[:500], statement_index))
            reads = self._reads(original, statement_index)
            return QueryLineage([], reads, [], issues, is_assignment)

        alias_map = _alias_map(qualified)
        outputs: list[OutputColumn] = []
        for index, (name, node) in enumerate(nodes.items()):
            hits = self._hits(node, alias_map)
            display = self._names.identifier(name)
            outputs.append(OutputColumn(index, display, _expr_sql(node.expression), hits))
        return QueryLineage(
            outputs,
            self._reads(original, statement_index),
            self._functions(qualified, statement_index),
            issues,
            is_assignment,
        )

    # -- leaves ----------------------------------------------------------------------------
    def _hits(self, root: Node, alias_map: dict[str, exp.Table]) -> list[SourceHit]:
        root_transform = _transform_of(root.expression)
        hits: list[SourceHit] = []
        seen: set[tuple] = set()

        def visit(node: Node, exact_so_far: bool, transform: str) -> None:
            if node.downstream:
                node_transform = _transform_of(node.expression)
                combined = _combine_transform(transform, node_transform)
                child_exact = exact_so_far and node_transform == "passthrough"
                for child in node.downstream:
                    visit(child, child_exact, combined)
                return
            for hit in self._leaf_hits(node, exact_so_far, transform, alias_map):
                key = (hit.table, hit.name, hit.column)
                if key not in seen:
                    seen.add(key)
                    hits.append(hit)

        visit(root, True, root_transform)
        return hits

    def _leaf_hits(
        self, leaf: Node, exact_path: bool, transform: str, alias_map: dict[str, exp.Table]
    ) -> list[SourceHit]:
        expression = leaf.expression
        if isinstance(expression, exp.Table):
            table = self._resolve_table(expression)
            display = self._names.table(expression)
            if leaf.name == "*" or leaf.name.endswith(".*"):
                return [SourceHit(table, display, "*", False, "star")]
            column = self._names.identifier(exp.to_column(leaf.name).name)
            return [SourceHit(table, display, column, exact_path, transform)]
        if isinstance(expression, exp.Placeholder):
            return [SourceHit(None, None, None, False, transform)]
        # Source-less leaf (COUNT(*), XML/hierarchyid method calls, ...): scan for columns.
        hits = []
        for alias, column in _column_like(expression):
            table_expr = alias_map.get(alias.casefold())
            if table_expr is None:
                continue
            table = self._resolve_table(table_expr)
            hits.append(
                SourceHit(
                    table,
                    self._names.table(table_expr),
                    self._names.identifier(column),
                    False,
                    "expression",
                )
            )
        return hits

    def _resolve_table(self, table: exp.Table) -> TableKey | None:
        return self.catalog.lookup(table.catalog or self.database, table.db or "dbo", table.name)

    # -- object references -----------------------------------------------------------------
    def _reads(self, query: exp.Expression, statement_index: int) -> list[ObjectRefEdge]:
        cte_names = {c.alias_or_name.casefold() for c in query.find_all(exp.CTE)}
        refs: dict[tuple, ObjectRefEdge] = {}
        for t in query.find_all(exp.Table):
            if not t.db and t.name.casefold() in cte_names:
                continue
            ref = self._ref("read", t, statement_index)
            refs.setdefault((ref.table, ref.name.casefold()), ref)
        return list(refs.values())

    def _ref(self, kind: str, table: exp.Table, statement_index: int) -> ObjectRefEdge:
        key = self._resolve_table(table)
        if key is not None:
            return ObjectRefEdge(kind, key, key.name, key.schema, statement_index, key.db)
        return ObjectRefEdge(
            kind,
            None,
            self._names.identifier(table.name),
            self._names.identifier(table.db) if table.db else None,
            statement_index,
            self._names.identifier(table.catalog) if table.catalog else None,
        )

    def _functions(self, qualified: exp.Expression, statement_index: int) -> list[ObjectRefEdge]:
        refs: dict[tuple[str, str], ObjectRefEdge] = {}
        for dot in qualified.find_all(exp.Dot):
            func = dot.expression
            owner = dot.this
            if isinstance(func, exp.Anonymous) and isinstance(owner, exp.Identifier):
                schema, name = owner.name, func.name
                refs.setdefault(
                    (schema.casefold(), name.casefold()),
                    ObjectRefEdge("function", None, name, schema, statement_index),
                )
        return list(refs.values())


# --- helpers ----------------------------------------------------------------------------


class _OriginalNames:
    """Original-case spellings from the query before sqlglot normalizes identifiers."""

    def __init__(self, query: exp.Expression) -> None:
        self._identifiers: dict[str, str] = {}
        self._tables: dict[tuple[str, str], str] = {}
        for ident in query.find_all(exp.Identifier):
            self._identifiers.setdefault(ident.name.casefold(), ident.name)
        for table in query.find_all(exp.Table):
            self._tables.setdefault(
                ((table.db or "").casefold(), table.name.casefold()),
                ".".join(p for p in (table.catalog, table.db, table.name) if p),
            )

    def identifier(self, name: str) -> str:
        return self._identifiers.get(name.casefold(), name)

    def table(self, table: exp.Table) -> str:
        key = ((table.db or "").casefold(), table.name.casefold())
        if key in self._tables:
            return self._tables[key]
        key = ("", table.name.casefold())  # qualification may have added the default schema
        return self._tables.get(key, _table_display(table))


def _column_like(expression: exp.Expression):
    """Yield (table_alias, column) for Column nodes and ``alias.col.method()`` Dot chains."""
    for column in expression.find_all(exp.Column):
        if column.table:
            yield column.table, column.name
    for dot in expression.find_all(exp.Dot):
        if isinstance(dot.this, exp.Identifier) and isinstance(dot.expression, exp.Identifier):
            yield dot.this.name, dot.expression.name


def _combine_transform(outer: str, inner: str) -> str:
    if "aggregate" in (outer, inner):
        return "aggregate"
    if "expression" in (outer, inner):
        return "expression"
    return outer if outer != "passthrough" else inner


def _rename_pseudo_tables(query: exp.Expression) -> None:
    """``#t`` -> ``sqldoc_temp.t`` and ``@tv`` -> ``sqldoc_tablevar.tv`` so they qualify."""
    for table in list(query.find_all(exp.Table)):
        ident = table.this
        if isinstance(ident, exp.Identifier) and ident.args.get("temporary"):
            table.set("this", exp.to_identifier(ident.name))
            table.set("db", exp.to_identifier(TEMP_SCHEMA))
        elif isinstance(ident, exp.Parameter):
            table.set("this", exp.to_identifier(ident.name))
            table.set("db", exp.to_identifier(TABLEVAR_SCHEMA))


def _rewrite_assignments(query: exp.Expression) -> bool:
    """``SELECT @v = expr`` -> ``SELECT expr AS _var_v``; returns True when any were found."""
    found = False
    for select in query.find_all(exp.Select):
        for projection in list(select.expressions):
            if isinstance(projection, exp.EQ) and isinstance(projection.this, exp.Parameter):
                found = True
                projection.replace(projection.expression.as_(f"_var_{projection.this.name}"))
    return found


def _alias_unnamed(query: exp.Expression) -> None:
    for select in query.find_all(exp.Select):
        for i, projection in enumerate(list(select.expressions)):
            if (
                isinstance(projection, exp.Star)
                or isinstance(projection, exp.Column)
                and projection.name == "*"
            ):
                continue
            if not projection.alias_or_name:
                projection.replace(projection.as_(f"_col{i}"))


def _alias_map(qualified: exp.Expression) -> dict[str, exp.Table]:
    return {(t.alias_or_name or t.name).casefold(): t for t in qualified.find_all(exp.Table)}


def _is_column_projection(expression: exp.Expression) -> bool:
    inner = expression.this if isinstance(expression, exp.Alias) else expression
    return isinstance(inner, exp.Column | exp.Star | exp.Table)


def _transform_of(expression: exp.Expression) -> str:
    inner = expression.this if isinstance(expression, exp.Alias) else expression
    if isinstance(inner, exp.Column | exp.Star):
        return "passthrough"
    if isinstance(inner, exp.AggFunc) or any(
        isinstance(n, exp.AggFunc) for n in inner.find_all(exp.AggFunc)
    ):
        return "aggregate"
    return "expression"


def _expr_sql(expression: exp.Expression) -> str:
    try:
        return expression.sql(dialect="tsql")[:MAX_EXPRESSION_SQL]
    except Exception:  # noqa: BLE001
        return ""


def _table_display(table: exp.Table) -> str:
    parts = [p for p in (table.catalog, table.db, table.name) if p]
    return ".".join(parts)


# --- objects ----------------------------------------------------------------------------


def map_outputs(
    ql: QueryLineage,
    output_columns: list[str] | None,
    statement_index: int,
    statement_kind: str,
    issues: list[Issue],
    catalog: LineageCatalog,
    via: str | None = None,
) -> list[ColumnEdge]:
    """Turn query outputs into edges targeting ``output_columns`` (positional, else by name)."""
    targets: dict[int, str] = {}
    if output_columns is None:
        targets = {o.index: o.name for o in ql.outputs}
    elif len(output_columns) == len(ql.outputs):
        targets = {o.index: output_columns[o.index] for o in ql.outputs}
    else:
        by_name = {c.casefold(): c for c in output_columns}
        for o in ql.outputs:
            if o.name.casefold() in by_name:
                targets[o.index] = by_name[o.name.casefold()]
        issues.append(
            Issue(
                "column_count_mismatch",
                f"query has {len(ql.outputs)} output columns but object has {len(output_columns)}",
                statement_index,
            )
        )
    edges: list[ColumnEdge] = []
    for o in ql.outputs:
        target = targets.get(o.index)
        if target is None:
            continue
        for hit in o.hits:
            edges.append(_edge(hit, target, o, catalog, statement_index, statement_kind, via))
    return edges


def _edge(
    hit: SourceHit,
    target: str,
    out: OutputColumn,
    catalog: LineageCatalog,
    statement_index: int,
    statement_kind: str,
    via: str | None,
) -> ColumnEdge:
    column = hit.column
    confidence = UNRESOLVED
    transform = hit.transform
    if hit.table is not None and column not in (None, "*"):
        known = catalog.column_name(hit.table, column)
        if known is not None:
            column = known
            confidence = EXACT if hit.exact_path and transform == "passthrough" else INFERRED
        else:
            confidence = INFERRED
        if hit.table.is_pseudo:
            transform = "temp"
    return ColumnEdge(
        target_column=target,
        target_index=out.index,
        source_table=hit.table,
        source_name=None if hit.table else hit.name,
        source_column=column,
        confidence=confidence,
        transform=transform,
        expression_sql=out.expression_sql,
        statement_index=statement_index,
        statement_kind=statement_kind,
        via=via,
    )


def analyze_view(
    definition: str,
    *,
    database: str,
    output_columns: list[str],
    catalog: LineageCatalog,
) -> LineageResult:
    result = LineageResult()
    query_text = view_query(definition)
    try:
        query = parse_one(query_text, read="tsql", error_level=ErrorLevel.RAISE)
    except (ParseError, SqlglotError) as exc:
        result.issues.append(Issue("parse_error", str(exc)[:500], 0, query_text[:200]))
        result.status = "failed"
        return result
    if not isinstance(query, exp.Query):
        result.issues.append(Issue("unsupported", "view body is not a query", 0, query_text[:200]))
        result.status = "failed"
        return result
    analyzer = QueryAnalyzer(catalog, database)
    ql = analyzer.analyze(query, statement_index=0)
    result.issues.extend(ql.issues)
    result.object_refs.extend(ql.reads)
    result.object_refs.extend(ql.functions)
    result.column_edges.extend(map_outputs(ql, output_columns, 0, "view", result.issues, catalog))
    return result.finalize()


# --- modules: procedures, functions, triggers -----------------------------------------------

_INSERTED_DELETED = ("inserted", "deleted")


@dataclass(frozen=True)
class _Target:
    kind: str  # table | temp | tablevar
    key: TableKey | None
    name: str


class _ModuleAnalysis:
    def __init__(
        self,
        catalog: LineageCatalog,
        database: str,
        kind: str,
        output_columns: list[str] | None,
        parent_table: TableKey | None,
    ) -> None:
        self.catalog = catalog
        self.database = database
        self.kind = kind
        self.output_columns = output_columns
        self.parent_table = parent_table
        self.symbols = SymbolTable(catalog, database)
        self.analyzer = QueryAnalyzer(catalog, database)
        self.result = LineageResult()
        self.return_var: str | None = None
        self._pseudo_trigger_tables: list[TableKey] = []
        self._vars: dict[str, list[SourceHit]] = {}  # @variable -> column hits flowing into it

    # -- entry -------------------------------------------------------------------------
    def run(self, definition: str) -> LineageResult:
        body = module_body(definition)
        try:
            if self.kind == "trigger" and self.parent_table is not None:
                cols = self.catalog.columns(self.parent_table)
                for pseudo in _INSERTED_DELETED:
                    if self.catalog.lookup(self.database, "dbo", pseudo) is None:
                        self._pseudo_trigger_tables.append(
                            self.catalog.add_table(self.database, "dbo", pseudo, cols)
                        )
            if self.kind == "table_function":
                self.return_var = rewrite.returns_table_variable(definition)
                if self.return_var and self.output_columns:
                    self.symbols.define("tablevar", self.return_var, self.output_columns)
            if self.kind == "inline_tvf":
                self._inline_tvf(body)
            else:
                for st in split_statements(body):
                    self._statement(st)
        finally:
            self.symbols.cleanup()
            for key in self._pseudo_trigger_tables:
                self.catalog.remove_table(key)
        self._post_process()
        return self.result.finalize()

    # -- statements -----------------------------------------------------------------------
    def _statement(self, st: Statement) -> None:
        handler = {
            "select": self._select,
            "insert": self._insert,
            "update": self._update,
            "merge": self._merge,
            "delete": self._delete,
            "exec": self._exec,
            "declare": self._declare,
            "create": self._create,
            "return": self._return,
            "set": self._set,
        }.get(st.kind)
        if handler is None:
            return
        try:
            handler(st)
        except (ParseError, SqlglotError) as exc:
            self._issue("parse_error", str(exc)[:500], st)
        except RecursionError as exc:
            self._issue("unsupported", f"expression too deep: {exc}", st)
        except Exception as exc:  # noqa: BLE001 - never let one statement kill the object
            self._issue("unsupported", f"{exc.__class__.__name__}: {str(exc)[:400]}", st)

    def _issue(self, kind: str, message: str, st: Statement | None) -> None:
        self.result.issues.append(
            Issue(kind, message, st.index if st else None, st.text[:200] if st else None)
        )

    def _parse(self, text: str) -> exp.Expression:
        return parse_one(text, read="tsql", error_level=ErrorLevel.RAISE)

    def _parse_dml(self, st: Statement) -> exp.Expression:
        try:
            return self._parse(st.text)
        except (ParseError, SqlglotError):
            stripped, changed = rewrite.strip_output_into(st.text)
            if not changed:
                raise
            expression = self._parse(stripped)
            self._issue("unsupported", "OUTPUT ... INTO clause ignored", st)
            return expression

    # -- SELECT ------------------------------------------------------------------------------
    def _select(self, st: Statement) -> None:
        query = self._parse_dml(st)
        if not isinstance(query, exp.Query):
            return
        into = query.args.get("into")
        if into is not None:
            query.set("into", None)
            target = self._target_of(into.this)
            ql = self._analyze(query, st)
            names = [o.name for o in ql.outputs]
            if target.kind in ("temp", "tablevar"):
                target = _Target(
                    target.kind, self.symbols.define(target.kind, target.name, names), target.name
                )
                self.analyzer.register_pseudo(target.key, names)
            self._emit(ql, target, names, st, "select_into")
            return
        ql = self._analyze(query, st)
        if ql.is_assignment:
            for out in ql.outputs:
                if out.name.casefold().startswith("_var_"):
                    self._vars.setdefault(out.name[5:].casefold(), []).extend(out.hits)
            return
        names = [o.name for o in ql.outputs]
        index = len(self.result.resultsets)
        self.result.resultsets.append(names)
        edges = map_outputs(ql, names, st.index, "select", self.result.issues, self.catalog)
        for e in edges:
            self.result.column_edges.append(
                _replace(e, target_kind="resultset", resultset_index=index)
            )

    # -- INSERT ------------------------------------------------------------------------------
    def _insert(self, st: Statement) -> None:
        ie = rewrite.match_insert_exec(st.text)
        if ie is not None:
            self._insert_exec(ie, st)
            return
        insert = self._parse_dml(st)
        if not isinstance(insert, exp.Insert):
            return
        this = insert.this
        columns: list[str] | None = None
        table_expr = this
        if isinstance(this, exp.Schema):
            table_expr = this.this
            columns = [rewrite.column_name(c) for c in this.expressions]
        target = self._target_of(table_expr)
        source = insert.expression
        if not isinstance(source, exp.Query):
            self._write_ref(target, st)
            return
        ql = self._analyze(source, st)
        if columns is None:
            columns = self._target_columns(target, [o.name for o in ql.outputs])
        if target.kind in ("temp", "tablevar") and target.key is None:
            key = self.symbols.define(target.kind, target.name, columns)
            self.analyzer.register_pseudo(key, columns)
            target = _Target(target.kind, key, target.name)
        self._emit(ql, target, columns, st, "insert")

    def _insert_exec(self, ie: rewrite.InsertExec, st: Statement) -> None:
        target = self._target_of(exp.to_table(ie.target, dialect="tsql"))
        self._write_ref(target, st)
        proc = exp.to_table(ie.proc, dialect="tsql")
        proc_ref = self._exec_ref(proc, st)
        columns = ie.columns or self._target_columns(target, [])
        for col in columns:
            self.result.column_edges.append(
                ColumnEdge(
                    target_column=col,
                    target_index=None,
                    source_table=None,
                    source_name=proc_ref.display(),
                    source_column="*",
                    confidence=UNRESOLVED,
                    transform="pseudo",
                    expression_sql=st.text[:MAX_EXPRESSION_SQL],
                    statement_index=st.index,
                    statement_kind="insert_exec",
                    target_kind=target.kind,
                    target_table=target.key,
                    target_name=None if target.key else target.name,
                )
            )

    # -- UPDATE / MERGE / DELETE ---------------------------------------------------------------
    def _update(self, st: Statement) -> None:
        update = self._parse_dml(st)
        if not isinstance(update, exp.Update):
            return
        table_expr, columns, sql = rewrite.update_to_select(update)
        target = self._target_of(table_expr)
        if not columns:  # e.g. SET [xml].modify(...) - nothing column-shaped to trace
            self._write_ref(target, st)
            return
        ql = self._analyze(self._parse(sql), st)
        self._emit(ql, target, columns, st, "update")

    def _merge(self, st: Statement) -> None:
        merge = self._parse_dml(st)
        if not isinstance(merge, exp.Merge):
            return
        table_expr, columns, sql = rewrite.merge_to_select(merge)
        target = self._target_of(table_expr)
        ql = self._analyze(self._parse(sql), st)
        self._emit(ql, target, columns, st, "merge")

    def _delete(self, st: Statement) -> None:
        delete = self._parse_dml(st)
        if not isinstance(delete, exp.Delete):
            return
        this = delete.this
        tables = delete.args.get("tables") or []
        target_expr = this
        if tables:
            target_expr = rewrite.resolve_alias(tables[0], this)
        target = self._target_of(rewrite.strip_alias(target_expr))
        self._write_ref(target, st)
        for t in this.find_all(exp.Table) if this is not None else []:
            key = self._lookup(t)
            if key is not None and key != target.key:
                self._add_ref(ObjectRefEdge("read", key, key.name, key.schema, st.index, key.db))
        for sub in delete.find_all(exp.Select):
            ql = self._analyze(sub, st)
            for r in ql.reads:
                self._add_ref(r)

    # -- EXEC / DECLARE / CREATE / RETURN ------------------------------------------------------
    def _exec(self, st: Statement) -> None:
        name = rewrite.exec_target(st.text)
        if name is None:
            self._dynamic(st)
            return
        self._exec_ref(exp.to_table(name, dialect="tsql"), st)

    def _dynamic(self, st: Statement) -> None:
        self.result.has_dynamic_sql = True
        self._issue("dynamic_sql", "dynamic SQL cannot be analyzed statically", st)

    def _declare(self, st: Statement) -> None:
        if "TABLE" not in st.text.upper():
            return
        declare = self._parse(st.text)
        if not isinstance(declare, exp.Declare):
            return
        for item in declare.expressions:
            kind = item.args.get("kind")
            names = item.this if isinstance(item.this, list) else [item.this]
            if isinstance(kind, exp.Schema):
                cols = [c.name for c in kind.expressions if isinstance(c, exp.ColumnDef)]
                for name_expr in names:
                    key = self.symbols.define("tablevar", name_expr.name, cols)
                    self.analyzer.register_pseudo(key, cols)

    def _create(self, st: Statement) -> None:
        if "#" not in st.text:
            return
        create = self._parse(st.text)
        if not isinstance(create, exp.Create) or not isinstance(create.this, exp.Schema):
            return
        table = create.this.this
        if isinstance(table, exp.Table) and table.this.args.get("temporary"):
            cols = [c.name for c in create.this.expressions if isinstance(c, exp.ColumnDef)]
            key = self.symbols.define("temp", table.name, cols)
            self.analyzer.register_pseudo(key, cols)

    def _set(self, st: Statement) -> None:
        assignment = rewrite.set_assignment(st.text)
        if assignment is None:
            return
        name, rhs = assignment
        hits: list[SourceHit] = []
        if rhs.upper().startswith(("(SELECT", "(WITH")):
            ql = self._analyze(self._parse(f"SELECT {rhs} AS _v"), st)
            for out in ql.outputs:
                hits.extend(out.hits)
        for var in rewrite.variable_refs(rhs):
            if var.casefold() != name.casefold():
                hits.extend(self._vars.get(var.casefold(), ()))
        # control flow is flattened, so assignments accumulate (conservative over-approximation)
        self._vars.setdefault(name.casefold(), []).extend(hits)

    def _return(self, st: Statement) -> None:
        if self.kind != "scalar_function":
            return
        inner = rewrite.return_expression(st.text)
        if not inner:
            return
        name = (self.output_columns or ["RETURN_VALUE"])[0]
        if inner.upper().lstrip().startswith(("SELECT", "WITH")):
            ql = self._analyze(self._parse(inner), st)
            for e in map_outputs(ql, [name], st.index, "return", self.result.issues, self.catalog):
                self.result.column_edges.append(_replace(e, target_kind="self"))
            return
        for var in rewrite.variable_refs(inner):
            for hit in self._vars.get(var.casefold(), ()):
                if hit.table is None or hit.column in (None, "*"):
                    continue
                column = self.catalog.column_name(hit.table, hit.column) or hit.column
                self.result.column_edges.append(
                    ColumnEdge(
                        target_column=name,
                        target_index=None,
                        source_table=hit.table,
                        source_name=None,
                        source_column=column,
                        confidence=INFERRED,
                        transform="aggregate" if hit.transform == "aggregate" else "expression",
                        expression_sql=st.text[:MAX_EXPRESSION_SQL],
                        statement_index=st.index,
                        statement_kind="return",
                        target_kind="self",
                    )
                )

    def _inline_tvf(self, body: str) -> None:
        statements = split_statements(body)
        st = next((s for s in statements if s.kind == "return"), None)
        inner = rewrite.return_expression(st.text) if st else None
        if not inner:
            self._issue("unsupported", "inline function without RETURN (SELECT ...)", st)
            return
        try:
            ql = self._analyze(self._parse(inner), st)
        except (ParseError, SqlglotError) as exc:
            self._issue("parse_error", str(exc)[:500], st)
            self.result.status = "failed"
            return
        edges = map_outputs(
            ql, self.output_columns, st.index, "return", self.result.issues, self.catalog
        )
        self.result.column_edges.extend(_replace(e, target_kind="self") for e in edges)

    # -- shared -------------------------------------------------------------------------------
    def _analyze(self, query: exp.Expression, st: Statement | None) -> QueryLineage:
        ql = self.analyzer.analyze(query, st.index if st else 0)
        self.result.issues.extend(ql.issues)
        for r in ql.reads:
            self._add_ref(r)
        for r in ql.functions:
            self._add_ref(r)
        return ql

    def _emit(
        self, ql: QueryLineage, target: _Target, columns: list[str], st: Statement, kind: str
    ) -> None:
        self._write_ref(target, st)
        edges = map_outputs(ql, columns, st.index, kind, self.result.issues, self.catalog)
        for e in edges:
            self.result.column_edges.append(
                _replace(
                    e,
                    target_kind=target.kind,
                    target_table=target.key,
                    target_name=None if target.key else target.name,
                )
            )

    def _target_columns(self, target: _Target, fallback: list[str]) -> list[str]:
        if target.key is not None:
            cols = self.catalog.columns(target.key)
            if cols:
                return cols
        return list(fallback)

    def _target_of(self, table: exp.Table) -> _Target:
        ident = table.this
        if isinstance(ident, exp.Identifier) and ident.args.get("temporary"):
            return _Target("temp", self.symbols.known("temp", ident.name), ident.name)
        if isinstance(ident, exp.Parameter):
            return _Target("tablevar", self.symbols.known("tablevar", ident.name), ident.name)
        key = self._lookup(table)
        return _Target("table", key, key.display() if key else _table_display(table))

    def _lookup(self, table: exp.Table) -> TableKey | None:
        return self.catalog.lookup(table.catalog or self.database, table.db or "dbo", table.name)

    def _write_ref(self, target: _Target, st: Statement) -> None:
        if target.kind != "table":
            return
        if target.key is not None:
            ref = ObjectRefEdge(
                "write", target.key, target.key.name, target.key.schema, st.index, target.key.db
            )
        else:
            parts = target.name.split(".")
            ref = ObjectRefEdge(
                "write", None, parts[-1], parts[-2] if len(parts) > 1 else None, st.index
            )
        self._add_ref(ref)

    def _exec_ref(self, proc: exp.Table, st: Statement) -> ObjectRefEdge:
        key = self._lookup(proc)
        if key is not None:
            ref = ObjectRefEdge("exec", key, key.name, key.schema, st.index, key.db)
        else:
            ref = ObjectRefEdge(
                "exec", None, proc.name, proc.db or "dbo", st.index, proc.catalog or None
            )
        self._add_ref(ref)
        return ref

    def _add_ref(self, ref: ObjectRefEdge) -> None:
        for existing in self.result.object_refs:
            if (
                existing.kind == ref.kind
                and existing.display().casefold() == ref.display().casefold()
            ):
                return
        self.result.object_refs.append(ref)

    def _post_process(self) -> None:
        edges: list[ColumnEdge] = []
        for e in self.result.column_edges:
            if (
                self.kind == "trigger"
                and e.source_table is not None
                and self.parent_table is not None
                and e.source_table.name.casefold() in _INSERTED_DELETED
                and e.source_table.schema.casefold() == "dbo"
            ):
                e = _replace(e, source_table=self.parent_table, via=e.source_table.name.casefold())
            if (
                self.return_var
                and e.target_kind == "tablevar"
                and e.target_table is not None
                and e.target_table.name.casefold() == self.return_var.lstrip("@").casefold()
            ):
                e = _replace(e, target_kind="self", target_table=None, target_name=None)
            edges.append(e)
        self.result.column_edges = edges
        if self.kind == "trigger":
            self.result.object_refs = [
                r
                for r in self.result.object_refs
                if not (r.kind == "read" and r.name.casefold() in _INSERTED_DELETED)
            ]


def _replace(edge: ColumnEdge, **changes) -> ColumnEdge:
    from dataclasses import replace

    return replace(edge, **changes)


def analyze_module(
    definition: str,
    *,
    kind: str,
    database: str,
    schema: str,
    name: str,
    catalog: LineageCatalog,
    output_columns: list[str] | None = None,
    parent_table: TableKey | None = None,
) -> LineageResult:
    """Lineage for procedures, functions and triggers (best effort, statement by statement)."""
    del schema, name  # identity is recorded by the caller; kept for a stable signature
    return _ModuleAnalysis(catalog, database, kind, output_columns, parent_table).run(definition)
