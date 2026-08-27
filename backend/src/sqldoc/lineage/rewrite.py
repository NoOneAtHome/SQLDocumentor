"""Rewrite writes (UPDATE / MERGE) into equivalent SELECT projections.

sqlglot's lineage() only accepts SELECT roots, so every write becomes
``(target, [target columns], SELECT <rhs AS col> ... FROM <sources>)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlglot import exp

_INSERT_EXEC = re.compile(
    r"^\s*INSERT\s+(?:INTO\s+)?(?P<target>[^\s(]+)\s*(?:\((?P<cols>[^)]*)\))?\s+"
    r"EXEC(?:UTE)?\s+(?P<proc>[^\s(;]+)",
    re.IGNORECASE | re.DOTALL,
)
_OUTPUT_INTO = re.compile(
    r"\bOUTPUT\b.*?\bINTO\b\s+[@#\[\]\w.]+(?:\s*\((?:[^()]|\([^()]*\))*\))?",
    re.IGNORECASE | re.DOTALL,
)
_DYNAMIC_EXEC = re.compile(r"^\s*EXEC(?:UTE)?\s*\(", re.IGNORECASE)
_EXEC_NAME = re.compile(r"^\s*EXEC(?:UTE)?\s+(?:@\w+\s*=\s*)?(?P<proc>[^\s(;,]+)", re.IGNORECASE)
_DYNAMIC_PROCS = frozenset({"sp_executesql", "xp_cmdshell"})
_RETURN = re.compile(r"^\s*RETURN\b", re.IGNORECASE)
_SET_VAR = re.compile(
    r"^\s*SET\s+@(?P<name>\w+)\s*(?:[-+*/%&|^]?=)\s*(?P<rhs>.*)$", re.IGNORECASE | re.DOTALL
)
_VAR_REF = re.compile(r"@(\w+)")
_RETURNS_TABLE_VAR = re.compile(r"\bRETURNS\s+(@\w+)\s+TABLE\b", re.IGNORECASE)


@dataclass(frozen=True)
class InsertExec:
    target: str
    columns: list[str] | None
    proc: str


def match_insert_exec(text: str) -> InsertExec | None:
    m = _INSERT_EXEC.match(text)
    if not m:
        return None
    cols = m.group("cols")
    columns = [c.strip().strip("[]") for c in cols.split(",")] if cols else None
    return InsertExec(m.group("target"), columns, m.group("proc"))


def strip_output_into(text: str) -> tuple[str, bool]:
    new, n = _OUTPUT_INTO.subn(" ", text)
    return new, n > 0


def is_dynamic_exec(text: str) -> bool:
    return bool(_DYNAMIC_EXEC.match(text))


def exec_target(text: str) -> str | None:
    """Procedure name of ``EXEC [@rc =] name ...`` (None for dynamic forms)."""
    if is_dynamic_exec(text):
        return None
    m = _EXEC_NAME.match(text)
    if not m:
        return None
    name = m.group("proc")
    if name.split(".")[-1].strip("[]").casefold() in _DYNAMIC_PROCS:
        return None
    return name


def return_expression(text: str) -> str | None:
    """Body of a RETURN statement with one balanced outer parenthesis pair removed."""
    if not _RETURN.match(text):
        return None
    inner = _RETURN.sub("", text, count=1).strip()
    if inner.startswith("(") and inner.endswith(")") and _balanced(inner[1:-1]):
        inner = inner[1:-1].strip()
    return inner or None


def set_assignment(text: str) -> tuple[str, str] | None:
    """``SET @v = <rhs>`` -> (v, rhs)."""
    m = _SET_VAR.match(text)
    return (m.group("name"), m.group("rhs").strip()) if m else None


def variable_refs(text: str) -> list[str]:
    """Names of ``@variables`` referenced in ``text`` (without the ``@``, deduplicated)."""
    seen: list[str] = []
    for name in _VAR_REF.findall(text):
        if name.casefold() not in {s.casefold() for s in seen} and not name.startswith("@"):
            seen.append(name)
    return seen


def returns_table_variable(definition: str) -> str | None:
    m = _RETURNS_TABLE_VAR.search(definition)
    return m.group(1) if m else None


def _balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def column_name(expression: exp.Expression) -> str:
    """``t.a`` / ``[a]`` / ``a`` -> ``a``."""
    if isinstance(expression, exp.Column):
        return expression.name
    if isinstance(expression, exp.Identifier):
        return expression.name
    if isinstance(expression, exp.Dot):
        return column_name(expression.expression)
    return expression.sql(dialect="tsql")


def update_to_select(update: exp.Update) -> tuple[exp.Table, list[str], str]:
    """Return (target table expression, target columns, SELECT sql) for an UPDATE."""
    from_ = update.args.get("from_")
    projections: list[str] = []
    columns: list[str] = []
    for assignment in update.expressions:
        if not isinstance(assignment, exp.EQ):
            continue
        columns.append(column_name(assignment.this))
        projections.append(f"{assignment.expression.sql(dialect='tsql')} AS [{columns[-1]}]")
    target = update.this
    if from_ is not None:
        source_sql = from_.this.sql(dialect="tsql")
        target = resolve_alias(target, from_.this)
    else:
        source_sql = update.this.sql(dialect="tsql")
    where = update.args.get("where")
    sql = f"SELECT {', '.join(projections) or '1 AS _none'} FROM {source_sql}"
    if where is not None:
        sql += f" {where.sql(dialect='tsql')}"
    return target, columns, sql


def merge_to_select(merge: exp.Merge) -> tuple[exp.Table, list[str], str]:
    target = merge.this
    using = merge.args["using"]
    on = merge.args.get("on")
    pairs: list[tuple[str, str]] = []
    whens = merge.args.get("whens")
    for when in whens.expressions if whens is not None else []:
        then = when.args.get("then")
        if isinstance(then, exp.Update):
            for assignment in then.expressions:
                if isinstance(assignment, exp.EQ):
                    pairs.append(
                        (column_name(assignment.this), assignment.expression.sql(dialect="tsql"))
                    )
        elif isinstance(then, exp.Insert):
            cols = then.this.expressions if isinstance(then.this, exp.Tuple) else []
            vals = then.expression.expressions if isinstance(then.expression, exp.Tuple) else []
            for col, val in zip(cols, vals, strict=False):
                pairs.append((column_name(col), val.sql(dialect="tsql")))
    seen: set[tuple[str, str]] = set()
    projections, columns = [], []
    for col, rhs in pairs:
        if (col.casefold(), rhs) in seen:
            continue
        seen.add((col.casefold(), rhs))
        columns.append(col)
        projections.append(f"{rhs} AS [{col}]")
    on_sql = f" ON {on.sql(dialect='tsql')}" if on is not None else ""
    sql = (
        f"SELECT {', '.join(projections) or '1 AS _none'} FROM {target.sql(dialect='tsql')} "
        f"JOIN {using.sql(dialect='tsql')}{on_sql}"
    )
    return strip_alias(target), columns, sql


def resolve_alias(target: exp.Table, source: exp.Expression) -> exp.Table:
    """``UPDATE t ... FROM Sales.T t`` -> the real ``Sales.T`` table."""
    if target.db:
        return target
    wanted = target.name.casefold()
    for table in source.find_all(exp.Table):
        if (table.alias or table.name).casefold() == wanted:
            return strip_alias(table)
    return target


def strip_alias(table: exp.Table) -> exp.Table:
    clean = table.copy()
    clean.set("alias", None)
    clean.set("joins", None)
    return clean
