import { useMemo } from 'react'
import { $api, scanPath } from '@/api/client'
import type { TableStatsRow, TableStatsSort } from '@/api/types'
import { ErrorState } from '@/components/ErrorState'
import { ObjectLink } from '@/components/ObjectLink'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { formatCompact, formatKb, formatNumber } from '@/lib/format'
import { routes } from '@/lib/routes'
import { STATS_QUERY_OPTS, useServerSort } from './useStatsQuery'

const SORTS: readonly TableStatsSort[] = ['rows', 'data_kb', 'index_kb', 'reserved_kb', 'size', 'partitions', 'name']

export function LargestTablesGrid({ scanId }: { scanId: number }) {
  const sort = useServerSort<TableStatsSort>('reserved_kb', SORTS)
  const q = $api.useQuery('get', '/api/scans/{scan_id}/stats/tables', { params: { path: scanPath(scanId), query: sort.query } }, STATS_QUERY_OPTS)
  const columns = useMemo<GridColumn<TableStatsRow>[]>(
    () => [
      { id: 'name', header: 'Table', minWidth: 260, sortable: true, cell: (r) => <ObjectLink id={r.object.id} db={r.object.db} schema={r.object.schema} kind={r.object.kind} name={r.object.name} showIcon className="text-[12.5px]" /> },
      { id: 'rows', header: 'Rows', width: 110, align: 'right', mono: true, sortable: true, cell: (r) => <span title={formatNumber(r.row_count)}>{formatCompact(r.row_count)}</span> },
      { id: 'data_kb', header: 'Data', width: 110, align: 'right', mono: true, sortable: true, cell: (r) => formatKb(r.data_kb) },
      { id: 'index_kb', header: 'Index', width: 110, align: 'right', mono: true, sortable: true, cell: (r) => formatKb(r.index_kb) },
      { id: 'reserved_kb', header: 'Reserved', width: 110, align: 'right', mono: true, sortable: true, cell: (r) => formatKb(r.reserved_kb) },
      {
        id: 'share',
        header: 'Share',
        width: 160,
        cell: (r) => {
          const max = q.data?.items[0]?.reserved_kb ?? r.reserved_kb ?? 0
          const pct = max ? Math.max(2, Math.round(((r.reserved_kb ?? 0) / max) * 100)) : 0
          return (
            <span className="flex items-center gap-2">
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                <span className="block h-full rounded-full bg-obj-table" style={{ width: `${pct}%` }} />
              </span>
            </span>
          )
        },
      },
      { id: 'storage', header: 'Storage', width: 120, cell: (r) => <span className="font-mono text-[11px] text-muted-foreground">{r.is_heap ? 'heap' : 'clustered'} · {(r.compression ?? 'none').toLowerCase()}</span> },
      { id: 'partitions', header: 'Parts', width: 70, align: 'right', mono: true, sortable: true, cell: (r) => r.partition_count ?? '—' },
    ],
    [q.data],
  )
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  return (
    <DataGrid
      aria-label="Largest tables"
      data={q.data?.items ?? []}
      columns={columns}
      rowKey={(r) => String(r.object.id)}
      loading={q.isPending}
      fetching={q.isFetching && !q.isPending}
      manualSorting
      sorting={sort.sorting}
      onSortingChange={sort.onSortingChange}
      rowHref={(r) => routes.object(scanId, r.object, 'stats')}
      maxHeight="calc(100vh - 220px)"
      emptyState="No storage stats in this snapshot — was the scan run with collect_stats?"
      footer={q.data ? `${formatNumber(q.data.total)} tables with storage stats` : undefined}
    />
  )
}
