"""Adapt raw catalog row dicts into the cascade module's dataclasses."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqldoc.mssql.catalog import object_kind
from sqldoc.scope.cascade import (
    CatalogObject,
    DependencyRow,
    ForeignKeyRow,
    SynonymRow,
    TriggerRow,
    Universe,
)


def universe_from_raw(objects_by_db: Mapping[str, Iterable[dict[str, Any]]]) -> Universe:
    objects: list[CatalogObject] = []
    for db, rows in objects_by_db.items():
        for r in rows:
            kind = object_kind(r["type"])
            if kind is None:
                continue
            objects.append(
                CatalogObject(
                    db=db,
                    object_id=int(r["object_id"]),
                    schema=r["schema_name"],
                    name=r["name"],
                    kind=kind,
                    parent_object_id=int(r["parent_object_id"])
                    if r.get("parent_object_id")
                    else None,
                )
            )
    return Universe(objects)


def dependencies_from_raw(db: str, rows: Iterable[dict[str, Any]]) -> list[DependencyRow]:
    return [
        DependencyRow(
            db=db,
            referencing_id=int(r["referencing_id"]),
            referencing_minor_id=int(r.get("referencing_minor_id") or 0),
            referenced_id=int(r["referenced_id"]) if r.get("referenced_id") is not None else None,
            referenced_server_name=r.get("referenced_server_name"),
            referenced_database_name=r.get("referenced_database_name"),
            referenced_schema_name=r.get("referenced_schema_name"),
            referenced_entity_name=r["referenced_entity_name"],
            is_caller_dependent=bool(r.get("is_caller_dependent")),
            is_ambiguous=bool(r.get("is_ambiguous")),
            is_schema_bound=bool(r.get("is_schema_bound_reference")),
        )
        for r in rows
    ]


def foreign_keys_from_raw(db: str, rows: Iterable[dict[str, Any]]) -> list[ForeignKeyRow]:
    return [
        ForeignKeyRow(
            db=db,
            fk_id=int(r["object_id"]),
            parent_object_id=int(r["parent_object_id"]),
            referenced_object_id=int(r["referenced_object_id"]),
        )
        for r in rows
    ]


def triggers_from_raw(db: str, rows: Iterable[dict[str, Any]]) -> list[TriggerRow]:
    return [
        TriggerRow(db=db, object_id=int(r["object_id"]), parent_id=int(r["parent_id"]))
        for r in rows
    ]


def synonyms_from_raw(db: str, rows: Iterable[dict[str, Any]]) -> list[SynonymRow]:
    return [
        SynonymRow(db=db, object_id=int(r["object_id"]), base_object_name=r["base_object_name"])
        for r in rows
    ]
