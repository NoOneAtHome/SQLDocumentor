import type { Confidence, EdgeKind, ObjectKind, ObjectScope } from '@/api/types'

export const OBJECT_KINDS: readonly ObjectKind[] = [
  'table',
  'view',
  'procedure',
  'scalar_function',
  'inline_tvf',
  'table_function',
  'clr_function',
  'trigger',
  'synonym',
  'sequence',
  'table_type',
  'temp_table',
  'external',
]

export const OBJECT_KIND_SET: ReadonlySet<string> = new Set(OBJECT_KINDS)

export const EDGE_KINDS: readonly EdgeKind[] = [
  'catalog',
  'fk',
  'trigger',
  'synonym',
  'parsed_read',
  'parsed_write',
  'parsed_exec',
]

export const EDGE_KIND_SET: ReadonlySet<string> = new Set(EDGE_KINDS)

export const SCOPES: readonly ObjectScope[] = ['in_scope', 'cascaded', 'external']

export const CONFIDENCES: readonly Confidence[] = ['exact', 'inferred', 'unresolved']

export const CONFIDENCE_RANK: Record<Confidence, number> = { exact: 2, inferred: 1, unresolved: 0 }

export const KIND_LABEL: Record<ObjectKind, string> = {
  table: 'Table',
  view: 'View',
  procedure: 'Procedure',
  scalar_function: 'Scalar function',
  inline_tvf: 'Inline TVF',
  table_function: 'Table function',
  clr_function: 'CLR function',
  trigger: 'Trigger',
  synonym: 'Synonym',
  sequence: 'Sequence',
  table_type: 'Table type',
  temp_table: 'Temp table',
  external: 'External',
}

export const KIND_LABEL_PLURAL: Record<ObjectKind, string> = {
  table: 'Tables',
  view: 'Views',
  procedure: 'Procedures',
  scalar_function: 'Scalar functions',
  inline_tvf: 'Inline TVFs',
  table_function: 'Table functions',
  clr_function: 'CLR functions',
  trigger: 'Triggers',
  synonym: 'Synonyms',
  sequence: 'Sequences',
  table_type: 'Table types',
  temp_table: 'Temp tables',
  external: 'External',
}

/** Colour family for each kind — resolves to the `--obj-*` CSS variables in index.css. */
export type KindColor = 'table' | 'view' | 'proc' | 'function' | 'trigger' | 'external' | 'misc'

export const KIND_COLOR: Record<ObjectKind, KindColor> = {
  table: 'table',
  view: 'view',
  procedure: 'proc',
  scalar_function: 'function',
  inline_tvf: 'function',
  table_function: 'function',
  clr_function: 'function',
  trigger: 'trigger',
  synonym: 'misc',
  sequence: 'misc',
  table_type: 'misc',
  temp_table: 'misc',
  external: 'external',
}

export const EDGE_KIND_LABEL: Record<EdgeKind, string> = {
  catalog: 'Catalog dependency',
  fk: 'Foreign key',
  trigger: 'Trigger',
  synonym: 'Synonym',
  parsed_read: 'Parsed read',
  parsed_write: 'Parsed write',
  parsed_exec: 'Parsed exec',
}

/** Label for an edge kind that may arrive as a plain string (e.g. `DepRef.edge_kind`). */
export function edgeKindLabel(kind: string): string {
  return EDGE_KIND_SET.has(kind) ? EDGE_KIND_LABEL[kind as EdgeKind] : kind
}

export function isObjectKind(kind: string | null | undefined): kind is ObjectKind {
  return !!kind && OBJECT_KIND_SET.has(kind)
}

export const SCOPE_LABEL: Record<ObjectScope, string> = {
  in_scope: 'In scope',
  cascaded: 'Cascaded',
  external: 'External',
}

export const SCAN_PHASES = [
  'connect',
  'enumerate',
  'cascade',
  'extract',
  'stats',
  'lineage',
  'finalize',
] as const

/** Query options for immutable, scan-scoped snapshot data. */
export const SNAPSHOT_QUERY = { staleTime: Infinity, gcTime: 30 * 60 * 1000 } as const

export const LINEAGE_MAX_NODES = 200
export const COLUMN_LINEAGE_MAX_NODES = 150
export const MAX_DEFINITION_HIGHLIGHT_BYTES = 200 * 1024
