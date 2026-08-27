"""Object identity: multipart T-SQL names and stable cross-scan keys."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectRef:
    server: str | None
    database: str | None
    schema: str | None
    name: str

    def display(self) -> str:
        parts = [self.server, self.database, self.schema, self.name]
        while parts and parts[0] is None:
            parts.pop(0)
        return ".".join(p or "" for p in parts)

    def matches(self, *, schema: str | None = None, name: str | None = None) -> bool:
        name_ok = name is None or self.name.casefold() == name.casefold()
        schema_ok = schema is None or (self.schema or "").casefold() == schema.casefold()
        return name_ok and schema_ok


def parse_multipart_name(text: str) -> ObjectRef:
    """Parse ``[server].[db].[schema].[name]`` (1-4 parts, bracket/quote aware)."""
    parts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(text)
    mode = "plain"  # plain | bracket | quote
    while i < n:
        ch = text[i]
        if mode == "plain":
            if ch == "[":
                mode = "bracket"
            elif ch == '"':
                mode = "quote"
            elif ch == ".":
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        elif mode == "bracket":
            if ch == "]":
                if i + 1 < n and text[i + 1] == "]":
                    buf.append("]")
                    i += 1
                else:
                    mode = "plain"
            else:
                buf.append(ch)
        else:  # quote
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    buf.append('"')
                    i += 1
                else:
                    mode = "plain"
            else:
                buf.append(ch)
        i += 1
    parts.append("".join(buf).strip())

    if not parts[-1]:
        raise ValueError(f"invalid object name: {text!r}")
    if len(parts) > 4:
        raise ValueError(f"too many name parts (max 4): {text!r}")
    padded: list[str | None] = [None] * (4 - len(parts)) + [p or None for p in parts]
    server, database, schema, name = padded
    assert name is not None
    return ObjectRef(server=server, database=database, schema=schema, name=name)


def object_key(connection: str, database: str, schema: str, name: str) -> str:
    return f"{connection}|{database}|{schema}|{name}"


def column_key(obj_key: str, column: str) -> str:
    return f"{obj_key}|{column}"


def external_key(server: str | None, database: str | None, schema: str | None, name: str) -> str:
    return f"external|{server or ''}|{database or ''}|{schema or ''}|{name}"


def temp_key(owner_key: str, name: str) -> str:
    return f"{owner_key}|#{name.lstrip('#')}"
