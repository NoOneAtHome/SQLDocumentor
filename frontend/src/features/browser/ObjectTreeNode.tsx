import { ChevronRight, Database, FolderTree } from 'lucide-react'
import { memo } from 'react'
import { Link } from 'react-router'
import type { ObjectKind } from '@/api/types'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { KIND_COLOR, KIND_LABEL_PLURAL } from '@/lib/constants'
import { formatCompact } from '@/lib/format'
import { cn } from '@/lib/utils'

export type TreeRow =
  | { type: 'db'; id: string; db: string; depth: 0; expanded: boolean; count: number; to: string }
  | { type: 'schema'; id: string; db: string; schema: string; depth: 1; expanded: boolean; count: number; selected: boolean; to: string }
  | { type: 'kind'; id: string; db: string; schema: string; kind: ObjectKind; depth: 2; expanded: boolean; count: number; loading: boolean; to: string }
  | { type: 'object'; id: string; db: string; schema: string; kind: ObjectKind; name: string; depth: 3; to: string; scope: string; hasIssues: boolean }
  | { type: 'more'; id: string; depth: 3; count: number; to: string }

interface Props {
  row: TreeRow
  active: boolean
  onToggle: (id: string) => void
  style?: React.CSSProperties
}

export const ObjectTreeNode = memo(function ObjectTreeNode({ row, active, onToggle, style }: Props) {
  const indent = 8 + row.depth * 12
  const base = 'flex h-7 w-full min-w-0 items-center gap-1.5 rounded-md pr-2 text-[12.5px] hover:bg-sidebar-accent'

  if (row.type === 'object') {
    return (
      <Link
        to={row.to}
        style={{ ...style, paddingLeft: indent + 18 }}
        aria-current={active ? 'page' : undefined}
        className={cn(base, 'font-mono', active && 'bg-sidebar-accent font-medium text-sidebar-accent-foreground')}
        title={`${row.schema}.${row.name}`}
      >
        <ObjectTypeIcon kind={row.kind} className={cn('size-3.5', row.scope === 'external' && 'opacity-60')} />
        <span className={cn('truncate', row.scope === 'cascaded' && 'text-sidebar-foreground/75')}>{row.name}</span>
        {row.hasIssues && <span className="ml-auto size-1.5 shrink-0 rounded-full bg-warning" title="Lineage issues" />}
      </Link>
    )
  }

  if (row.type === 'more') {
    return (
      <Link to={row.to} style={{ ...style, paddingLeft: indent + 18 }} className={cn(base, 'text-muted-foreground')}>
        … {formatCompact(row.count)} more — open list
      </Link>
    )
  }

  const label = row.type === 'db' ? row.db : row.type === 'schema' ? row.schema : KIND_LABEL_PLURAL[row.kind]
  const kindColor = row.type === 'kind' ? KIND_COLOR[row.kind] : undefined
  return (
    <div style={{ ...style, paddingLeft: indent }} className={cn(base, 'group/tree')}>
      <button
        type="button"
        aria-label={row.expanded ? `Collapse ${label}` : `Expand ${label}`}
        aria-expanded={row.expanded}
        onClick={() => onToggle(row.id)}
        className="flex size-4 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-sidebar-border/70 hover:text-foreground"
      >
        <ChevronRight className={cn('size-3.5 transition-transform', row.expanded && 'rotate-90')} />
      </button>
      {row.type === 'db' && <Database className="size-3.5 shrink-0 text-obj-table" />}
      {row.type === 'schema' && <FolderTree className={cn('size-3.5 shrink-0', row.selected ? 'text-primary' : 'text-muted-foreground')} />}
      {row.type === 'kind' && <span data-kind-color={kindColor} className="size-2 shrink-0 rounded-full bg-(--kind)" />}
      <Link
        to={row.to}
        className={cn('min-w-0 flex-1 truncate', row.type === 'db' && 'font-mono font-medium', row.type === 'schema' && 'font-mono', active && 'font-medium text-sidebar-accent-foreground')}
        onClick={(e) => {
          if (!row.expanded) {
            e.preventDefault()
            onToggle(row.id)
          }
        }}
        onDoubleClick={(e) => e.preventDefault()}
      >
        {label}
      </Link>
      <span className="ml-auto shrink-0 font-mono text-[11px] text-muted-foreground tnum">
        {row.type === 'kind' && row.loading ? '…' : formatCompact(row.count)}
      </span>
    </div>
  )
})
