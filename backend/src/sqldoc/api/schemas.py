"""Pydantic response/request models - the API contract the SPA generates its types from.

Names match the design spec (``ObjectSummary``, ``ObjectDetail``, ``Column``, ``Index``,
``TableStats``, ``ExecStats``, ``MissingIndex``, ``ScanSummary``, ``LineageGraph`` ...).
Optional fields are ``X | None`` so the generated TypeScript carries ``| null``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EdgeKind = Literal[
    "catalog", "fk", "trigger", "synonym", "parsed_read", "parsed_write", "parsed_exec"
]
Confidence = Literal["exact", "inferred", "unresolved"]

ObjectKind = Literal[
    "table",
    "view",
    "procedure",
    "scalar_function",
    "inline_tvf",
    "table_function",
    "clr_function",
    "trigger",
    "synonym",
    "sequence",
    "table_type",
    "temp_table",
    "external",
]
Scope = Literal["in_scope", "cascaded", "external"]
LineageStatus = Literal["ok", "partial", "failed", "skipped", "pending", "n/a"]
ColumnKind = Literal["column", "resultset", "return_value"]
Resolution = Literal["resolved", "caller_dependent", "ambiguous", "external", "unresolved"]
Transform = Literal["passthrough", "expression", "aggregate", "star", "temp", "pseudo", "computed"]
ScanStatusValue = Literal["running", "succeeded", "failed", "cancelled"]
ScanPhase = Literal["connect", "enumerate", "cascade", "extract", "stats", "lineage", "finalize"]
AuthMode = Literal["sql", "integrated"]
DriverSetting = Literal["auto", "pyodbc", "pymssql"]
DriverUsed = Literal["pyodbc", "pymssql"]
IssueKind = Literal[
    "parse_error",
    "qualify_failed",
    "lineage_failed",
    "dynamic_sql",
    "unsupported",
    "column_count_mismatch",
    "skipped",
    "timeout",
    "unresolved_ref",
]
AnnotationTarget = Literal["object", "column"]


class ListEnvelope[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


# -- app ---------------------------------------------------------------------------------


class Health(BaseModel):
    ok: bool
    version: str
    db_path: str


class ConfigOut(BaseModel):
    config_path: str
    sqlite_path: str
    config: dict[str, Any]


# -- connections -------------------------------------------------------------------------


class ScanOptionsOut(BaseModel):
    cascade_foreign_keys: bool = True
    include_triggers_of_cascaded_tables: bool = True
    collect_stats: bool = True
    parse_lineage: bool = True


class ScanCounts(BaseModel):
    databases: int = 0
    schemas: int = 0
    tables: int = 0
    views: int = 0
    procedures: int = 0
    functions: int = 0
    triggers: int = 0
    synonyms: int = 0
    externals: int = 0
    cascaded: int = 0
    columns: int = 0
    edges_object: int = 0
    edges_column: int = 0
    lineage_issues: int = 0
    warnings: int = 0


class ScanSummary(BaseModel):
    id: int
    connection: str
    status: ScanStatusValue
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    options: ScanOptionsOut | None = None
    counts: ScanCounts | None = None
    error: str | None = None
    server_name: str | None = None
    server_version: str | None = None
    server_edition: str | None = None
    auth_scheme: str | None = None
    driver: DriverUsed | None = None


class ConnectionDatabase(BaseModel):
    name: str
    schemas: list[str]


class ConnectionInfo(BaseModel):
    name: str
    host: str
    port: int
    auth_mode: AuthMode
    username: str | None = None
    driver: DriverSetting
    databases: list[ConnectionDatabase]
    latest_scan: ScanSummary | None = None
    running_scan_id: int | None = None


class ConnectionTestDatabase(BaseModel):
    name: str
    reachable: bool
    can_view_definition: bool | None = None
    can_view_database_state: bool | None = None
    error: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    server_name: str | None = None
    version: str | None = None
    edition: str | None = None
    auth_scheme: str | None = None
    driver: DriverUsed | None = None
    can_view_server_state: bool | None = None
    databases: list[ConnectionTestDatabase] = Field(default_factory=list)
    error: str | None = None


# -- scans -------------------------------------------------------------------------------


class ScanStartRequest(BaseModel):
    collect_stats: bool | None = None
    parse_lineage: bool | None = None
    cascade_foreign_keys: bool | None = None
    include_triggers_of_cascaded_tables: bool | None = None


class ScanStarted(BaseModel):
    scan_id: int


class ScanCancelled(BaseModel):
    scan_id: int
    cancelled: bool


class ScanProgressInfo(BaseModel):
    phase: ScanPhase | None = None
    phase_index: int = 0
    phase_count: int = 7
    current: int = 0
    total: int = 0
    message: str = ""
    updated_at: datetime | None = None


class ScanWarningOut(BaseModel):
    phase: ScanPhase
    code: str
    message: str
    database: str | None = None


class ScanLogEntry(BaseModel):
    ts: str
    level: str
    message: str


class ScanStatus(ScanSummary):
    progress: ScanProgressInfo
    warnings: list[ScanWarningOut] = Field(default_factory=list)
    log: list[ScanLogEntry] = Field(default_factory=list)


class SchemaOverview(BaseModel):
    name: str
    is_selected: bool
    counts_by_kind: dict[str, int]


class DatabaseOverview(BaseModel):
    name: str
    is_configured: bool
    schemas: list[SchemaOverview]


class WarningsSummary(BaseModel):
    lineage_issues: int = 0
    unused_indexes: int = 0
    missing_index_suggestions: int = 0
    external_refs: int = 0


class ScanOverview(BaseModel):
    databases: list[DatabaseOverview]
    counts: ScanCounts
    lineage_coverage: float | None = None
    warnings_summary: WarningsSummary
    warnings: list[ScanWarningOut] = Field(default_factory=list)


# -- catalog -----------------------------------------------------------------------------


class ObjectSummary(BaseModel):
    id: int
    object_key: str
    db: str | None = None
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str
    kind: ObjectKind
    scope: Scope
    description: str | None = None
    annotation_description: str | None = None
    tags: list[str] = Field(default_factory=list)
    row_count: int | None = None
    total_size_kb: int | None = None
    exec_count: int | None = None
    modified_at: datetime | None = None
    lineage_status: LineageStatus
    has_lineage_issues: bool = False

    model_config = {"populate_by_name": True}


class ObjectRef(BaseModel):
    id: int
    db: str | None = None
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str
    kind: ObjectKind

    model_config = {"populate_by_name": True}


class ParentRef(BaseModel):
    id: int
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str
    kind: ObjectKind

    model_config = {"populate_by_name": True}


class FkTarget(BaseModel):
    object_id: int
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str
    column: str

    model_config = {"populate_by_name": True}


class ColumnLineageCounts(BaseModel):
    upstream: int = 0
    downstream: int = 0


class Column(BaseModel):
    id: int
    ordinal: int
    name: str
    column_kind: ColumnKind
    type_display: str | None = None
    is_nullable: bool | None = None
    is_identity: bool | None = None
    is_computed: bool | None = None
    computed_definition: str | None = None
    default_definition: str | None = None
    collation: str | None = None
    in_primary_key: bool = False
    fk_to: FkTarget | None = None
    ms_description: str | None = None
    description: str | None = None
    lineage: ColumnLineageCounts


class Parameter(BaseModel):
    id: int
    parameter_id: int
    name: str
    type_display: str | None = None
    is_output: bool | None = None
    has_default_value: bool | None = None
    default_value: str | None = None
    is_readonly: bool | None = None
    is_table_type: bool | None = None
    is_return_value: bool = False
    description: str | None = None


class IndexKeyColumn(BaseModel):
    name: str
    desc: bool = False


class IndexUsage(BaseModel):
    seeks: int = 0
    scans: int = 0
    lookups: int = 0
    updates: int = 0
    last_seek: datetime | None = None
    last_scan: datetime | None = None
    last_lookup: datetime | None = None
    last_update: datetime | None = None


class Index(BaseModel):
    id: int
    name: str | None = None
    type_desc: str | None = None
    is_unique: bool | None = None
    is_primary_key: bool | None = None
    is_unique_constraint: bool | None = None
    key_columns: list[IndexKeyColumn] = Field(default_factory=list)
    included_columns: list[str] = Field(default_factory=list)
    filter: str | None = None
    is_disabled: bool | None = None
    usage: IndexUsage | None = None
    is_unused: bool = False
    description: str | None = None


class KeyConstraint(BaseModel):
    name: str | None = None
    type_desc: str | None = None
    columns: list[str] = Field(default_factory=list)


class ForeignKeyColumnPair(BaseModel):
    column: str
    referenced_column: str


class ForeignKeyRef(BaseModel):
    id: int
    name: str
    parent: ObjectRef
    referenced: ObjectRef
    columns: list[ForeignKeyColumnPair] = Field(default_factory=list)
    delete_action: str | None = None
    update_action: str | None = None
    is_disabled: bool | None = None
    is_not_trusted: bool | None = None


class CheckConstraint(BaseModel):
    id: int
    name: str
    column: str | None = None
    definition: str | None = None
    is_disabled: bool | None = None
    is_not_trusted: bool | None = None


class ObjectKeys(BaseModel):
    primary_key: KeyConstraint | None = None
    unique_constraints: list[KeyConstraint] = Field(default_factory=list)
    foreign_keys_out: list[ForeignKeyRef] = Field(default_factory=list)
    foreign_keys_in: list[ForeignKeyRef] = Field(default_factory=list)
    check_constraints: list[CheckConstraint] = Field(default_factory=list)


class TriggerRef(BaseModel):
    id: int
    name: str
    events: str | None = None
    is_instead_of: bool | None = None
    is_disabled: bool | None = None


class TableStats(BaseModel):
    kind: Literal["table"] = "table"
    row_count: int | None = None
    data_kb: int | None = None
    index_kb: int | None = None
    reserved_kb: int | None = None
    partition_count: int | None = None
    is_heap: bool | None = None
    compression: str | None = None
    stats_as_of: datetime | None = None


class ExecStats(BaseModel):
    kind: Literal["exec"] = "exec"
    exec_count: int | None = None
    total_ms: float | None = None
    avg_ms: float | None = None
    min_ms: float | None = None
    max_ms: float | None = None
    total_cpu_ms: float | None = None
    total_logical_reads: int | None = None
    last_exec_at: datetime | None = None
    cached_since: datetime | None = None
    since_server_start: datetime | None = None


class MissingIndex(BaseModel):
    id: int
    equality_columns: str | None = None
    inequality_columns: str | None = None
    included_columns: str | None = None
    user_seeks: int | None = None
    user_scans: int | None = None
    last_user_seek: datetime | None = None
    avg_cost: float | None = None
    avg_impact: float | None = None
    improvement_measure: float | None = None
    suggested_ddl: str | None = None


class DepRef(BaseModel):
    object_id: int | None = None
    db: str | None = None
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str
    kind: ObjectKind | None = None
    scope: Scope | None = None
    edge_kind: str
    resolution: Resolution
    referenced_name: str | None = None

    model_config = {"populate_by_name": True}


class Dependencies(BaseModel):
    uses: list[DepRef] = Field(default_factory=list)
    used_by: list[DepRef] = Field(default_factory=list)


class LineageCounts(BaseModel):
    upstream: int = 0
    downstream: int = 0
    columns_with_lineage: int = 0


class LineageIssue(BaseModel):
    kind: IssueKind
    statement_index: int | None = None
    message: str
    snippet: str | None = None


class Annotation(BaseModel):
    target_kind: AnnotationTarget
    target_key: str
    connection: str | None = None
    db: str | None = None
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str | None = None
    column: str | None = None
    description: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"populate_by_name": True}


class ObjectDetail(BaseModel):
    summary: ObjectSummary
    sql_object_id: int | None = None
    ms_description: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    parent: ParentRef | None = None
    definition_length: int = 0
    has_dynamic_sql: bool = False
    is_schema_bound: bool | None = None
    trigger_events: str | None = None
    is_instead_of_trigger: bool | None = None
    is_disabled: bool | None = None
    external_server: str | None = None
    columns: list[Column] = Field(default_factory=list)
    parameters: list[Parameter] = Field(default_factory=list)
    indexes: list[Index] = Field(default_factory=list)
    keys: ObjectKeys
    triggers: list[TriggerRef] = Field(default_factory=list)
    stats: TableStats | ExecStats | None = Field(default=None, discriminator="kind")
    missing_indexes: list[MissingIndex] = Field(default_factory=list)
    dependencies: Dependencies
    lineage_counts: LineageCounts
    lineage_issues: list[LineageIssue] = Field(default_factory=list)
    annotation: Annotation | None = None
    column_annotations: dict[str, Annotation] = Field(default_factory=dict)


class Definition(BaseModel):
    definition: str | None = None
    length: int = 0
    has_dynamic_sql: bool = False


class SearchMatch(BaseModel):
    field: str
    snippet: str | None = None


class SearchObjectHit(ObjectSummary):
    match: SearchMatch


class SearchColumnHit(BaseModel):
    object: ObjectSummary
    column: str
    data_type: str | None = None


class SearchResult(BaseModel):
    objects: list[SearchObjectHit] = Field(default_factory=list)
    columns: list[SearchColumnHit] = Field(default_factory=list)


# -- lineage -----------------------------------------------------------------------------


class LineageMore(BaseModel):
    upstream: int = 0
    downstream: int = 0


class LineageNode(BaseModel):
    id: str
    object_id: int
    db: str | None = None
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str
    kind: ObjectKind
    scope: Scope
    hop: int
    row_count: int | None = None
    exec_count: int | None = None
    has_lineage_issues: bool = False
    more: LineageMore

    model_config = {"populate_by_name": True}


class LineageEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: EdgeKind
    resolution: Resolution
    detail: str | None = None


class LineageGraph(BaseModel):
    focus: str
    nodes: list[LineageNode]
    edges: list[LineageEdge]
    truncated: bool = False
    total: int = 0


class ColumnLineageFocus(BaseModel):
    object_id: int
    column: str | None = None


class ColumnLineageNodeColumn(BaseModel):
    column_id: int
    name: str
    data_type: str | None = None


class ColumnLineageNode(BaseModel):
    id: str
    object_id: int
    db: str | None = None
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str
    kind: ObjectKind
    scope: Scope
    hop: int
    has_lineage_issues: bool = False
    more: LineageMore
    columns: list[ColumnLineageNodeColumn] = Field(default_factory=list)
    column_count_total: int = 0

    model_config = {"populate_by_name": True}


class ColumnLineageEdge(BaseModel):
    id: str
    source: str
    source_column: str
    target: str
    target_column: str
    confidence: Confidence
    transform: Transform
    via_object_id: int | None = None
    via_name: str | None = None
    expression: str | None = None


class ColumnLineageGraph(BaseModel):
    focus: ColumnLineageFocus
    nodes: list[ColumnLineageNode]
    edges: list[ColumnLineageEdge]
    truncated: bool = False
    total: int = 0


class ConfidenceCounts(BaseModel):
    exact: int = 0
    inferred: int = 0
    unresolved: int = 0


class ObjectColumnLineage(BaseModel):
    column_id: int
    name: str
    upstream_count: int = 0
    downstream_count: int = 0
    confidences: ConfidenceCounts


class LineageHub(BaseModel):
    object_id: int
    db: str | None = None
    schema_: str | None = Field(default=None, alias="schema", serialization_alias="schema")
    name: str
    kind: str
    upstream: int
    downstream: int
    degree: int

    model_config = {"populate_by_name": True}


class LineageSummary(BaseModel):
    objects: int
    edges_by_kind: dict[str, int]
    column_edges_by_confidence: dict[str, int]
    lineage_coverage: float | None = None
    objects_with_issues: int = 0
    top_hubs: list[LineageHub] = Field(default_factory=list)


class LineageIssueItem(LineageIssue):
    id: int
    object: ObjectRef


# -- stats grids -------------------------------------------------------------------------


class TableStatsRow(BaseModel):
    object: ObjectSummary
    row_count: int | None = None
    data_kb: int | None = None
    index_kb: int | None = None
    reserved_kb: int | None = None
    partition_count: int | None = None
    is_heap: bool | None = None
    compression: str | None = None


class IndexStatsRow(BaseModel):
    object: ObjectSummary
    index_id: int
    index_name: str | None = None
    type_desc: str | None = None
    is_unique: bool | None = None
    is_primary_key: bool | None = None
    is_unique_constraint: bool | None = None
    key_columns: list[str] = Field(default_factory=list)
    included_columns: list[str] = Field(default_factory=list)
    seeks: int = 0
    scans: int = 0
    lookups: int = 0
    updates: int = 0
    last_seek: datetime | None = None
    last_scan: datetime | None = None
    last_lookup: datetime | None = None
    last_update: datetime | None = None
    is_unused: bool = False


class ProcStatsRow(BaseModel):
    object: ObjectSummary
    exec_count: int | None = None
    total_ms: float | None = None
    avg_ms: float | None = None
    min_ms: float | None = None
    max_ms: float | None = None
    total_cpu_ms: float | None = None
    total_logical_reads: int | None = None
    last_exec_at: datetime | None = None
    cached_since: datetime | None = None


class MissingIndexRow(MissingIndex):
    object: ObjectSummary


# -- annotations -------------------------------------------------------------------------


class AnnotationUpsert(BaseModel):
    connection: str = Field(min_length=1)
    db: str = Field(min_length=1)
    schema_: str = Field(min_length=1, alias="schema")
    name: str = Field(min_length=1)
    column: str | None = None
    description: str | None = None
    notes: str | None = None
    tags: list[str] | None = None

    model_config = {"populate_by_name": True}


class TagInfo(BaseModel):
    tag: str
    color: str | None = None
    count: int = 0
