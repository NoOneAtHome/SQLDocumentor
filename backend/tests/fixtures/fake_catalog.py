"""Builder for in-memory catalogs used by cascade tests."""

from __future__ import annotations

from sqldoc.scope.cascade import (
    CatalogObject,
    DependencyRow,
    ForeignKeyRow,
    SynonymRow,
    TriggerRow,
    Universe,
)


class FakeCatalog:
    def __init__(self) -> None:
        self.objects: list[CatalogObject] = []
        self.deps: list[DependencyRow] = []
        self.fks: list[ForeignKeyRow] = []
        self.triggers: list[TriggerRow] = []
        self.synonyms: list[SynonymRow] = []
        self._next_id = 100

    def _add(self, db: str, schema: str, name: str, kind: str, parent: int | None = None) -> int:
        oid = self._next_id
        self._next_id += 1
        self.objects.append(
            CatalogObject(
                db=db, object_id=oid, schema=schema, name=name, kind=kind, parent_object_id=parent
            )
        )
        return oid

    def table(self, db: str, schema: str, name: str) -> int:
        return self._add(db, schema, name, "table")

    def view(self, db: str, schema: str, name: str) -> int:
        return self._add(db, schema, name, "view")

    def proc(self, db: str, schema: str, name: str) -> int:
        return self._add(db, schema, name, "procedure")

    def function(self, db: str, schema: str, name: str) -> int:
        return self._add(db, schema, name, "scalar_function")

    def trigger(self, db: str, schema: str, name: str, parent: int) -> int:
        oid = self._add(db, schema, name, "trigger", parent=parent)
        self.triggers.append(TriggerRow(db=db, object_id=oid, parent_id=parent))
        return oid

    def synonym(self, db: str, schema: str, name: str, base: str) -> int:
        oid = self._add(db, schema, name, "synonym")
        self.synonyms.append(SynonymRow(db=db, object_id=oid, base_object_name=base))
        return oid

    def dep(
        self,
        db: str,
        referencing_id: int,
        *,
        referenced_id: int | None = None,
        entity: str,
        schema: str | None = None,
        database: str | None = None,
        server: str | None = None,
        minor_id: int = 0,
        ambiguous: bool = False,
        caller_dependent: bool = False,
    ) -> None:
        self.deps.append(
            DependencyRow(
                db=db,
                referencing_id=referencing_id,
                referencing_minor_id=minor_id,
                referenced_id=referenced_id,
                referenced_server_name=server,
                referenced_database_name=database,
                referenced_schema_name=schema,
                referenced_entity_name=entity,
                is_caller_dependent=caller_dependent,
                is_ambiguous=ambiguous,
            )
        )

    def resolved_dep(
        self, db: str, referencing_id: int, referenced_id: int, minor_id: int = 0
    ) -> None:
        target = next(o for o in self.objects if o.db == db and o.object_id == referenced_id)
        self.dep(
            db,
            referencing_id,
            referenced_id=referenced_id,
            entity=target.name,
            schema=target.schema,
            minor_id=minor_id,
        )

    def fk(self, db: str, parent: int, referenced: int) -> None:
        self.fks.append(
            ForeignKeyRow(
                db=db, fk_id=self._next_id, parent_object_id=parent, referenced_object_id=referenced
            )
        )
        self._next_id += 1

    def universe(self) -> Universe:
        return Universe(self.objects)
