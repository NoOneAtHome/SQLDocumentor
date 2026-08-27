"""Annotations & tags: user descriptions/notes/tags keyed by stable object/column keys.

Keys are built exactly like ``sqldoc.mssql.identity.object_key`` / ``column_key``
(``connection|db|schema|name[|column]``) and compared case-insensitively, so they
survive rescans. When the latest succeeded scan knows the object, the catalog's
spelling is used for the stored key.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.orm import Session

from sqldoc.api import build
from sqldoc.api import schemas as S
from sqldoc.api.deps import SessionDep
from sqldoc.mssql.identity import column_key, object_key
from sqldoc.store import repo

router = APIRouter(tags=["annotations"])


def resolve_target(
    session: Session, connection: str, db: str, schema: str, name: str, column: str | None
) -> tuple[str, str]:
    """(target_kind, target_key), preferring catalog case from the latest scan."""
    latest = repo.latest_scan(session, connection)
    obj = repo.lookup_object(session, latest.id, db, schema, name) if latest else None
    key = obj.object_key if obj is not None else object_key(connection, db, schema, name)
    if column is None or not column.strip():
        return "object", key
    if obj is not None:
        col = repo.column_by_name(session, latest.id, obj.id, column)
        if col is not None:
            return "column", col.column_key
    return "column", column_key(key, column)


@router.put("/annotations", response_model=S.Annotation)
def put_annotation(body: S.AnnotationUpsert, session: SessionDep) -> S.Annotation:
    kind, key = resolve_target(
        session, body.connection, body.db, body.schema_, body.name, body.column
    )
    fields = body.model_fields_set
    kwargs = {}
    if "description" in fields:
        kwargs["description"] = body.description
    if "notes" in fields:
        kwargs["notes"] = body.notes
    ann = repo.upsert_annotation(session, kind, key, **kwargs)
    if "tags" in fields:
        repo.set_tags(session, kind, ann.target_key, body.tags or [])
    tags = repo.tag_names_for(session, kind, ann.target_key)
    session.commit()
    return build.annotation_out(kind, ann.target_key, ann, tags)


@router.delete("/annotations", status_code=204, response_class=Response)
def delete_annotation(
    session: SessionDep,
    connection: str,
    db: str,
    schema: str,
    name: str,
    column: str | None = None,
) -> Response:
    kind, key = resolve_target(session, connection, db, schema, name, column)
    if not repo.delete_annotation(session, kind, key):
        raise HTTPException(status_code=404, detail=f"no annotation for {key}")
    session.commit()
    return Response(status_code=204)


@router.get("/annotations", response_model=S.ListEnvelope[S.Annotation])
def list_annotations(
    session: SessionDep,
    connection: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> S.ListEnvelope[S.Annotation]:
    entries, total = repo.list_annotations(
        session, connection=connection, tag=tag, q=q, limit=limit, offset=offset
    )
    items = [
        build.annotation_out(e.target_kind, e.target_key, e.annotation, e.tags) for e in entries
    ]
    return S.ListEnvelope(items=items, total=total, limit=limit, offset=offset)


@router.get("/tags", response_model=list[S.TagInfo])
def list_tags(session: SessionDep, connection: str | None = None) -> list[S.TagInfo]:
    return [
        S.TagInfo(tag=t.name, color=t.color, count=t.count)
        for t in repo.list_tags(session, connection)
    ]
