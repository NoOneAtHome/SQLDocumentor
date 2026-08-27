"""SQLAlchemy 2.0 models for the SQLite snapshot store.

Every scan is an immutable snapshot: all snapshot tables carry ``scan_id`` with
``ON DELETE CASCADE`` so pruning a scan is a single delete. Annotations and tags
are *not* scan-scoped; they key on stable ``object_key`` / ``column_key`` strings
compared case-insensitively. All datetimes are naive UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NOCASE = String(collation="NOCASE")


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite has no timezone type)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _scan_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_name: Mapped[str] = mapped_column(index=True)
    status: Mapped[str]  # running | succeeded | failed | cancelled
    phase: Mapped[str | None]
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    server_name: Mapped[str | None]
    server_version: Mapped[str | None]
    server_edition: Mapped[str | None]
    server_start_time: Mapped[datetime | None] = mapped_column(DateTime)
    auth_scheme: Mapped[str | None]
    driver: Mapped[str | None]
    options_json: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[str | None] = mapped_column(Text)  # secrets stripped
    summary_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class SnapshotDatabase(Base):
    __tablename__ = "databases"
    __table_args__ = (UniqueConstraint("scan_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    name: Mapped[str]
    database_id: Mapped[int | None]
    collation: Mapped[str | None]
    compatibility_level: Mapped[int | None]
    is_configured: Mapped[bool] = mapped_column(Boolean, default=True)
    selected_schemas_json: Mapped[str | None] = mapped_column(Text)
    has_view_definition: Mapped[bool | None]
    has_view_database_state: Mapped[bool | None]


class DbObject(Base):
    __tablename__ = "objects"
    __table_args__ = (
        UniqueConstraint("scan_id", "object_key"),
        Index("ix_objects_scan_kind", "scan_id", "kind"),
        Index("ix_objects_scan_schema", "scan_id", "schema_name"),
        Index("ix_objects_scan_sql_object_id", "scan_id", "sql_object_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    database_id: Mapped[int | None] = mapped_column(
        ForeignKey("databases.id", ondelete="CASCADE"), index=True
    )
    object_key: Mapped[str] = mapped_column(NOCASE, index=True)
    database_name: Mapped[str | None]
    schema_name: Mapped[str | None]
    name: Mapped[str]
    kind: Mapped[str]
    sql_object_id: Mapped[int | None]
    scope: Mapped[str]  # in_scope | cascaded | external
    parent_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE")
    )
    external_server: Mapped[str | None]
    base_object_name: Mapped[str | None]
    create_date: Mapped[datetime | None] = mapped_column(DateTime)
    modify_date: Mapped[datetime | None] = mapped_column(DateTime)
    description: Mapped[str | None] = mapped_column(Text)
    definition: Mapped[str | None] = mapped_column(Text)
    uses_ansi_nulls: Mapped[bool | None]
    uses_quoted_identifier: Mapped[bool | None]
    is_schema_bound: Mapped[bool | None]
    is_instead_of_trigger: Mapped[bool | None]
    trigger_events: Mapped[str | None]
    is_disabled: Mapped[bool | None]
    has_dynamic_sql: Mapped[bool] = mapped_column(Boolean, default=False)
    lineage_status: Mapped[str] = mapped_column(default="n/a")  # ok|partial|failed|skipped|n/a


class Column(Base):
    __tablename__ = "columns"
    __table_args__ = (
        UniqueConstraint("scan_id", "column_key"),
        Index("ix_columns_scan_object", "scan_id", "object_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    column_key: Mapped[str] = mapped_column(NOCASE, index=True)
    column_id: Mapped[int | None]
    ordinal: Mapped[int]
    name: Mapped[str]
    column_kind: Mapped[str] = mapped_column(default="column")  # column|resultset|return_value
    resultset_index: Mapped[int | None]
    type_name: Mapped[str | None]
    type_display: Mapped[str | None]
    system_type_name: Mapped[str | None]
    type_schema: Mapped[str | None]
    is_user_defined_type: Mapped[bool | None]
    max_length: Mapped[int | None]
    precision: Mapped[int | None]
    scale: Mapped[int | None]
    is_nullable: Mapped[bool | None]
    is_identity: Mapped[bool | None]
    identity_seed: Mapped[str | None]
    identity_increment: Mapped[str | None]
    is_computed: Mapped[bool | None]
    computed_definition: Mapped[str | None] = mapped_column(Text)
    is_persisted: Mapped[bool | None]
    default_name: Mapped[str | None]
    default_definition: Mapped[str | None] = mapped_column(Text)
    collation_name: Mapped[str | None]
    is_rowguidcol: Mapped[bool | None]
    generated_always_type: Mapped[int | None]
    description: Mapped[str | None] = mapped_column(Text)


class Parameter(Base):
    __tablename__ = "parameters"
    __table_args__ = (Index("ix_parameters_scan_object", "scan_id", "object_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    parameter_id: Mapped[int]
    name: Mapped[str]
    type_name: Mapped[str | None]
    type_display: Mapped[str | None]
    max_length: Mapped[int | None]
    precision: Mapped[int | None]
    scale: Mapped[int | None]
    is_output: Mapped[bool | None]
    has_default_value: Mapped[bool | None]
    default_value: Mapped[str | None]
    is_readonly: Mapped[bool | None]
    is_table_type: Mapped[bool | None]
    is_return_value: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)


class IndexDef(Base):
    __tablename__ = "indexes"
    __table_args__ = (Index("ix_indexes_scan_object", "scan_id", "object_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    index_id: Mapped[int]
    name: Mapped[str | None]
    type_code: Mapped[int | None]
    type_desc: Mapped[str | None]
    is_unique: Mapped[bool | None]
    is_primary_key: Mapped[bool | None]
    is_unique_constraint: Mapped[bool | None]
    has_filter: Mapped[bool | None]
    filter_definition: Mapped[str | None] = mapped_column(Text)
    fill_factor: Mapped[int | None]
    is_disabled: Mapped[bool | None]
    is_padded: Mapped[bool | None]
    data_space_name: Mapped[str | None]
    data_space_type: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)


class IndexColumn(Base):
    __tablename__ = "index_columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    index_id: Mapped[int] = mapped_column(ForeignKey("indexes.id", ondelete="CASCADE"), index=True)
    column_id: Mapped[int | None] = mapped_column(ForeignKey("columns.id", ondelete="CASCADE"))
    column_name: Mapped[str]
    key_ordinal: Mapped[int | None]
    is_descending: Mapped[bool | None]
    is_included: Mapped[bool | None]
    partition_ordinal: Mapped[int | None]


class ForeignKeyDef(Base):
    __tablename__ = "foreign_keys"
    __table_args__ = (
        Index("ix_fk_scan_parent", "scan_id", "parent_object_id"),
        Index("ix_fk_scan_referenced", "scan_id", "referenced_object_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    name: Mapped[str]
    parent_object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    referenced_object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    delete_action: Mapped[str | None]
    update_action: Mapped[str | None]
    is_disabled: Mapped[bool | None]
    is_not_trusted: Mapped[bool | None]


class ForeignKeyColumn(Base):
    __tablename__ = "foreign_key_columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    foreign_key_id: Mapped[int] = mapped_column(
        ForeignKey("foreign_keys.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int]
    parent_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("columns.id", ondelete="CASCADE")
    )
    parent_column_name: Mapped[str]
    referenced_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("columns.id", ondelete="CASCADE")
    )
    referenced_column_name: Mapped[str]


class CheckConstraintDef(Base):
    __tablename__ = "check_constraints"
    __table_args__ = (Index("ix_checks_scan_object", "scan_id", "object_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    column_id: Mapped[int | None] = mapped_column(ForeignKey("columns.id", ondelete="CASCADE"))
    name: Mapped[str]
    definition: Mapped[str | None] = mapped_column(Text)
    is_disabled: Mapped[bool | None]
    is_not_trusted: Mapped[bool | None]


class ObjectDependency(Base):
    """Object-level edge, direction source -> target (data flows to / source uses target).

    ``edge_kind``: catalog | fk | trigger | synonym | parsed_read | parsed_write | parsed_exec
    ``resolution``: resolved | caller_dependent | ambiguous | external | unresolved
    """

    __tablename__ = "object_dependencies"
    __table_args__ = (
        Index("ix_deps_scan_source", "scan_id", "source_object_id"),
        Index("ix_deps_scan_target", "scan_id", "target_object_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    source_object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    target_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE")
    )
    edge_kind: Mapped[str]
    resolution: Mapped[str] = mapped_column(default="resolved")
    is_ambiguous: Mapped[bool] = mapped_column(Boolean, default=False)
    is_caller_dependent: Mapped[bool] = mapped_column(Boolean, default=False)
    is_schema_bound: Mapped[bool] = mapped_column(Boolean, default=False)
    referencing_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("columns.id", ondelete="CASCADE")
    )
    referenced_name: Mapped[str | None]


class ColumnLineage(Base):
    """Column-level edge: source column -> target column (data flows to)."""

    __tablename__ = "column_lineage"
    __table_args__ = (
        Index("ix_col_lineage_scan_source", "scan_id", "source_column_id"),
        Index("ix_col_lineage_scan_target", "scan_id", "target_column_id"),
        Index("ix_col_lineage_scan_target_obj", "scan_id", "target_object_id"),
        Index("ix_col_lineage_scan_source_obj", "scan_id", "source_object_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    source_object_id: Mapped[int | None] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE")
    )
    source_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("columns.id", ondelete="CASCADE")
    )
    source_column_name: Mapped[str | None]
    target_object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    target_column_id: Mapped[int] = mapped_column(ForeignKey("columns.id", ondelete="CASCADE"))
    via_object_id: Mapped[int | None] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    confidence: Mapped[str]  # exact | inferred | unresolved
    transform: Mapped[str]  # passthrough|expression|aggregate|star|temp|pseudo|computed
    statement_index: Mapped[int | None]
    statement_kind: Mapped[str | None]
    expression_sql: Mapped[str | None] = mapped_column(Text)
    via: Mapped[str | None]


class TableStats(Base):
    __tablename__ = "table_stats"
    __table_args__ = (UniqueConstraint("scan_id", "object_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    row_count: Mapped[int | None]
    data_kb: Mapped[int | None]
    index_kb: Mapped[int | None]
    reserved_kb: Mapped[int | None]
    partition_count: Mapped[int | None]
    is_heap: Mapped[bool | None]
    compression: Mapped[str | None]


class IndexUsage(Base):
    __tablename__ = "index_usage"
    __table_args__ = (UniqueConstraint("scan_id", "index_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    index_id: Mapped[int] = mapped_column(ForeignKey("indexes.id", ondelete="CASCADE"))
    user_seeks: Mapped[int] = mapped_column(Integer, default=0)
    user_scans: Mapped[int] = mapped_column(Integer, default=0)
    user_lookups: Mapped[int] = mapped_column(Integer, default=0)
    user_updates: Mapped[int] = mapped_column(Integer, default=0)
    last_user_seek: Mapped[datetime | None] = mapped_column(DateTime)
    last_user_scan: Mapped[datetime | None] = mapped_column(DateTime)
    last_user_lookup: Mapped[datetime | None] = mapped_column(DateTime)
    last_user_update: Mapped[datetime | None] = mapped_column(DateTime)
    is_unused: Mapped[bool] = mapped_column(Boolean, default=False)


class ProcStats(Base):
    __tablename__ = "proc_stats"
    __table_args__ = (UniqueConstraint("scan_id", "object_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    execution_count: Mapped[int | None]
    total_elapsed_us: Mapped[int | None]
    avg_elapsed_us: Mapped[int | None]
    min_elapsed_us: Mapped[int | None]
    max_elapsed_us: Mapped[int | None]
    total_cpu_us: Mapped[int | None]
    total_logical_reads: Mapped[int | None]
    last_execution_time: Mapped[datetime | None] = mapped_column(DateTime)
    cached_time: Mapped[datetime | None] = mapped_column(DateTime)


class MissingIndex(Base):
    __tablename__ = "missing_indexes"
    __table_args__ = (Index("ix_missing_scan_object", "scan_id", "object_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    index_handle: Mapped[int | None]
    equality_columns: Mapped[str | None]
    inequality_columns: Mapped[str | None]
    included_columns: Mapped[str | None]
    unique_compiles: Mapped[int | None]
    user_seeks: Mapped[int | None]
    user_scans: Mapped[int | None]
    last_user_seek: Mapped[datetime | None] = mapped_column(DateTime)
    avg_total_user_cost: Mapped[float | None] = mapped_column(Float)
    avg_user_impact: Mapped[float | None] = mapped_column(Float)
    improvement_measure: Mapped[float | None] = mapped_column(Float)
    suggested_ddl: Mapped[str | None] = mapped_column(Text)


class LineageIssue(Base):
    __tablename__ = "lineage_issues"
    __table_args__ = (Index("ix_issues_scan_object", "scan_id", "object_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    statement_index: Mapped[int | None]
    kind: Mapped[
        str
    ]  # parse_error|qualify_failed|dynamic_sql|unsupported|column_count_mismatch|skipped|timeout
    message: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(Text)


class ScanWarning(Base):
    __tablename__ = "scan_warnings"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = _scan_fk()
    phase: Mapped[str]
    database_name: Mapped[str | None]
    code: Mapped[str]
    message: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (UniqueConstraint("target_kind", "target_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target_kind: Mapped[str]  # object | column
    target_key: Mapped[str] = mapped_column(NOCASE, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(NOCASE, unique=True)
    color: Mapped[str | None]


class TagAssignment(Base):
    __tablename__ = "tag_assignments"
    __table_args__ = (UniqueConstraint("tag_id", "target_kind", "target_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    target_kind: Mapped[str]
    target_key: Mapped[str] = mapped_column(NOCASE, index=True)


class Meta(Base):
    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
