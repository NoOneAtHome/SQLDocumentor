"""Split a T-SQL module body into statements without relying on semicolons.

sqlglot's parser only splits batches on ``;`` and most real procedure bodies
have none, so we walk the token stream ourselves: a statement starts at depth 0
on a starter keyword, with continuation rules for the constructs where a
starter keyword legitimately appears mid-statement (``UPDATE ... SET``,
``INSERT ... SELECT``, ``UNION SELECT``, CTE-prefixed DML, ``MERGE ... ;``).
Only DML statements (``is_dml``) are handed to sqlglot later.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import tokenize
from sqlglot.dialects.tsql import TSQL
from sqlglot.errors import TokenError
from sqlglot.tokens import Token, TokenType

_COMMAND_TYPES = frozenset(TSQL.Tokenizer.COMMANDS)

DML_KINDS = frozenset({"select", "insert", "update", "delete", "merge", "exec"})

_STARTERS: dict[str, str] = {
    "SELECT": "select",
    "INSERT": "insert",
    "UPDATE": "update",
    "DELETE": "delete",
    "MERGE": "merge",
    "WITH": "with",
    "EXEC": "exec",
    "EXECUTE": "exec",
    "DECLARE": "declare",
    "SET": "set",
    "IF": "if",
    "ELSE": "else",
    "WHILE": "while",
    "BEGIN": "begin",
    "END": "end",
    "RETURN": "return",
    "PRINT": "print",
    "RAISERROR": "raiserror",
    "THROW": "throw",
    "TRUNCATE": "truncate",
    "CREATE": "create",
    "DROP": "drop",
    "ALTER": "alter",
    "OPEN": "open",
    "FETCH": "fetch",
    "CLOSE": "close",
    "DEALLOCATE": "deallocate",
    "COMMIT": "commit",
    "ROLLBACK": "rollback",
    "GOTO": "goto",
    "BREAK": "break",
    "CONTINUE": "continue",
    "WAITFOR": "waitfor",
    "USE": "use",
}

_SET_OPERATORS = {"UNION", "EXCEPT", "INTERSECT", "ALL"}
_INSERT_CONTINUATIONS = {"SELECT", "EXEC", "EXECUTE", "VALUES", "DEFAULT", "WITH", "OUTPUT"}
_CTE_DML = {
    "SELECT": "select",
    "INSERT": "insert",
    "UPDATE": "update",
    "DELETE": "delete",
    "MERGE": "merge",
}
_NOT_WORDS = {TokenType.STRING, TokenType.IDENTIFIER, TokenType.NUMBER}
_NAME_PREFIXES = {TokenType.PARAMETER, TokenType.HASH, TokenType.DOT}


@dataclass(frozen=True)
class Statement:
    index: int
    kind: str
    start: int
    end: int
    text: str

    @property
    def is_dml(self) -> bool:
        return self.kind in DML_KINDS


def _tokens(text: str, base: int = 0) -> list[Token]:
    """Tokenize T-SQL, undoing sqlglot's "command mode".

    After ``END`` / ``FETCH`` / ``PRINT``-style keywords sqlglot swallows the rest of the
    statement (up to ``;``) into one STRING token carrying the raw source text (with
    meaningless offsets). Such tokens are re-tokenized recursively at their real position.
    """
    out: list[Token] = []
    prev: Token | None = None
    cursor = 0
    for tok in tokenize(text, read="tsql"):
        if (
            tok.token_type == TokenType.STRING
            and prev is not None
            and prev.token_type in _COMMAND_TYPES
            and tok.text
        ):
            real_start = text.find(tok.text, cursor)
            if real_start >= 0:
                out.extend(_tokens(tok.text, base + real_start))
                cursor = real_start + len(tok.text)
                prev = out[-1] if out else None
                continue
        if base:
            tok = Token(
                tok.token_type,
                tok.text,
                tok.line,
                tok.col,
                tok.start + base,
                tok.end + base,
                tok.comments,
            )
        out.append(tok)
        prev = tok
        cursor = max(cursor, tok.end - base + 1)
    return out


def split_statements(body: str) -> list[Statement]:
    if not body.strip():
        return []
    try:
        tokens = _tokens(body)
    except TokenError:
        return [_fallback(body)]
    if not tokens:
        return []

    statements: list[Statement] = []
    start_tok: Token | None = None
    kind = ""
    depth = 0
    case_depth = 0
    in_merge = False
    expecting_cte_dml = False
    after_insert = False
    update_set_seen = False
    prev: Token | None = None

    def close(last: Token) -> None:
        if start_tok is not None:
            statements.append(
                Statement(
                    index=len(statements),
                    kind=kind,
                    start=start_tok.start,
                    end=last.end + 1,
                    text=body[start_tok.start : last.end + 1],
                )
            )

    for pos, tok in enumerate(tokens):
        tt = tok.token_type
        next_tok = tokens[pos + 1] if pos + 1 < len(tokens) else None
        if tt == TokenType.L_PAREN:
            depth += 1
        elif tt == TokenType.R_PAREN:
            depth = max(depth - 1, 0)
        elif tt == TokenType.SEMICOLON:
            if prev is not None:
                close(prev)
            start_tok, kind = None, ""
            in_merge = expecting_cte_dml = after_insert = update_set_seen = False
            prev = tok
            continue

        word = _word(tok, prev)
        starts_new = False
        if word is not None and depth == 0:
            if word == "CASE":
                case_depth += 1
            elif word == "END" and case_depth:
                case_depth -= 1
            elif (word == "ELSE" and case_depth) or in_merge:
                pass
            elif expecting_cte_dml and word in _CTE_DML:
                kind = _CTE_DML[word]
                expecting_cte_dml = False
                in_merge = kind == "merge"
                after_insert = kind == "insert"
            elif after_insert and word in _INSERT_CONTINUATIONS:
                after_insert = word in ("OUTPUT", "WITH")  # hints/OUTPUT precede the source
            elif word == "SET" and kind == "update" and not update_set_seen:
                update_set_seen = True
            elif word == "SELECT" and prev is not None and _text(prev) in _SET_OPERATORS:
                pass
            elif (
                word == "UPDATE"
                and next_tok is not None
                and next_tok.token_type == TokenType.L_PAREN
            ):
                pass  # trigger predicate UPDATE(column), not an UPDATE statement
            elif word in _STARTERS:
                starts_new = True
        elif word == "CASE":
            case_depth += 1
        elif word == "END" and case_depth:
            case_depth -= 1

        if starts_new:
            if prev is not None and start_tok is not None:
                close(prev)
            start_tok = tok
            kind = _STARTERS[word]
            in_merge = kind == "merge"
            expecting_cte_dml = kind == "with"
            after_insert = kind == "insert"
            update_set_seen = False
        elif start_tok is None:
            start_tok, kind = tok, "other"
        prev = tok

    if prev is not None:
        close(prev)
    return statements


def _word(tok: Token, prev: Token | None) -> str | None:
    if tok.token_type in _NOT_WORDS:
        return None
    if prev is not None and prev.token_type in _NAME_PREFIXES:
        return None
    text = tok.text
    if not text or not (text[0].isalpha() or text[0] == "_"):
        return None
    return text.split()[0].upper()  # sqlglot merges some keywords ("BEGIN CATCH", "END TRY")


def _text(tok: Token) -> str:
    return tok.text.upper() if tok.token_type not in _NOT_WORDS else ""


def _fallback(body: str) -> Statement:
    first = body.strip().split(None, 1)[0].upper() if body.strip() else ""
    return Statement(
        index=0, kind=_STARTERS.get(first, "other"), start=0, end=len(body), text=body.strip()
    )


def module_body(definition: str) -> str:
    """Text after the ``AS`` that ends a CREATE PROC/FUNCTION/TRIGGER/VIEW header."""
    try:
        tokens = _tokens(definition)
    except TokenError:
        return definition
    depth = 0
    prev: Token | None = None
    for tok in tokens:
        if tok.token_type == TokenType.L_PAREN:
            depth += 1
        elif tok.token_type == TokenType.R_PAREN:
            depth = max(depth - 1, 0)
        elif (
            depth == 0
            and _word(tok, prev) == "AS"
            and (prev is None or _text(prev) not in ("EXEC", "EXECUTE"))
        ):
            return definition[tok.end + 1 :]
        prev = tok
    return definition


def view_query(definition: str) -> str:
    """The SELECT (possibly CTE-prefixed) that defines a view, without CHECK OPTION."""
    body = module_body(definition)
    statements = split_statements(body)
    for s in statements:
        if s.kind == "select":
            return s.text
    return body.strip()
