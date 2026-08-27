import type { ObjectKind } from '@/api/types'
import type { ObjectTab } from '@/lib/routes'

export const TAB_LABEL: Record<ObjectTab, string> = {
  overview: 'Overview',
  columns: 'Columns',
  indexes: 'Indexes',
  keys: 'Keys',
  parameters: 'Parameters',
  definition: 'Definition',
  stats: 'Stats',
  lineage: 'Lineage',
  notes: 'Notes',
}

/** Tabs per object kind (from the spec). */
export function tabsForKind(kind: ObjectKind): ObjectTab[] {
  switch (kind) {
    case 'table':
      return ['overview', 'columns', 'indexes', 'keys', 'stats', 'lineage', 'notes']
    case 'view':
      return ['overview', 'columns', 'indexes', 'definition', 'lineage', 'notes']
    case 'procedure':
    case 'scalar_function':
    case 'clr_function':
      return ['overview', 'parameters', 'definition', 'stats', 'lineage', 'notes']
    case 'inline_tvf':
    case 'table_function':
      return ['overview', 'parameters', 'columns', 'definition', 'stats', 'lineage', 'notes']
    case 'trigger':
      return ['overview', 'definition', 'lineage', 'notes']
    case 'table_type':
    case 'temp_table':
      return ['overview', 'columns', 'lineage', 'notes']
    case 'external':
    case 'synonym':
    case 'sequence':
    default:
      return ['overview', 'lineage', 'notes']
  }
}

export function isRoutine(kind: ObjectKind): boolean {
  return kind === 'procedure' || kind === 'scalar_function' || kind === 'inline_tvf' || kind === 'table_function' || kind === 'clr_function' || kind === 'trigger'
}

export function hasDefinition(kind: ObjectKind): boolean {
  return kind === 'view' || isRoutine(kind)
}
