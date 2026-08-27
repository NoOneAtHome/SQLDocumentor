import type { SortingState } from '@tanstack/react-table'
import { useMemo } from 'react'
import type { ObjectSort, ObjectSummary, SortOrder } from '@/api/types'
import { KindBadge, LineageStatusBadge, ScopeBadge, TagChip } from '@/components/ObjectBadge'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { RelativeTime } from '@/components/RelativeTime'
import { formatCompact, formatKb, formatNumber } from '@/lib/format'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'

interface Props {
  scanId: number
  items: ObjectSummary[]
  total: number
  loading?: boolean
  fetching?: boolean
  sort: ObjectSort
  order: SortOrder
  onSortChange: (sort: ObjectSort, order: SortOrder) => void
  showSchema?: boolean
  showKind?: boolean
  emptyState?: React.ReactNode
  maxHeight?: number | string
}

const SORT_IDS: Record<string, ObjectSort> = { name: 'name', kind: 'kind', rows: 'rows', size: 'size', modified: 'modified' }

/** Server-sorted object grid (name · kind · scope · rows · size · execs · modified · lineage). */
export function ObjectListGrid({ scanId, items, total, loading, fetching, sort, order, onSortChange, showSchema = true, showKind = true, emptyState, maxHeight }: Props) {
  const sorting = useMemo<SortingState>(() => [{ id: sort, desc: order === 'desc' }], [sort, order])
  const columns = useMemo<GridColumn<ObjectSummary>[]>(
    () => [
      {
        id: 'name',
        header: 'Name',
        minWidth: 260,
        sortable: true,
        cell: (o) => (
          <span className="flex min-w-0 items-center gap-2">
            <ObjectTypeIcon kind={o.kind} className="size-3.5" />
            <span className={cn('truncate font-mono text-[12.5px]', o.scope === 'cascaded' && 'text-foreground/80')}>
              {showSchema && <span className="text-muted-foreground">{o.schema}.</span>}
              {o.name}
            </span>
            <ScopeBadge scope={o.scope} className="h-4 text-[10px]" />
            {(o.tags ?? []).map((t) => (
              <TagChip key={t} tag={t} className="h-4 text-[10px]" />
            ))}
          </span>
        ),
      },
      ...(showKind ? [{ id: 'kind', header: 'Kind', width: 130, sortable: true, cell: (o: ObjectSummary) => <KindBadge kind={o.kind} /> } satisfies GridColumn<ObjectSummary>] : []),
      { id: 'rows', header: 'Rows', width: 96, align: 'right', mono: true, sortable: true, cell: (o) => (o.row_count != null ? <span title={formatNumber(o.row_count)}>{formatCompact(o.row_count)}</span> : <span className="text-muted-foreground">—</span>) },
      { id: 'size', header: 'Size', width: 96, align: 'right', mono: true, sortable: true, cell: (o) => (o.total_size_kb != null ? formatKb(o.total_size_kb) : <span className="text-muted-foreground">—</span>) },
      { id: 'execs', header: 'Execs', width: 90, align: 'right', mono: true, cell: (o) => (o.exec_count != null ? formatCompact(o.exec_count) : <span className="text-muted-foreground">—</span>) },
      { id: 'modified', header: 'Modified', width: 120, sortable: true, cell: (o) => <RelativeTime value={o.modified_at} className="text-muted-foreground" /> },
      { id: 'lineage', header: 'Lineage', width: 130, cell: (o) => <LineageStatusBadge status={o.lineage_status} hasIssues={o.has_lineage_issues} /> },
      {
        id: 'description',
        header: 'Description',
        minWidth: 200,
        cell: (o) => <span className="truncate text-[12.5px] text-muted-foreground">{o.annotation_description ?? o.description ?? ''}</span>,
      },
    ],
    [showSchema, showKind],
  )

  return (
    <DataGrid
      aria-label="Objects"
      data={items}
      columns={columns}
      rowKey={(o) => String(o.id)}
      loading={loading}
      fetching={fetching}
      manualSorting
      sorting={sorting}
      onSortingChange={(s) => {
        const first = s[0]
        if (!first) onSortChange('name', 'asc')
        else onSortChange(SORT_IDS[first.id] ?? 'name', first.desc ? 'desc' : 'asc')
      }}
      rowHref={(o) => routes.object(scanId, o)}
      emptyState={emptyState ?? 'No objects match.'}
      maxHeight={maxHeight}
      footer={total > items.length ? `Showing ${formatNumber(items.length)} of ${formatNumber(total)} — narrow the search to see the rest.` : `${formatNumber(total)} objects`}
    />
  )
}
