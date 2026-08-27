import { useMemo } from 'react'
import { $api, scanPath } from '@/api/client'
import type { ProcStatsRow, ProcStatsSort } from '@/api/types'
import { ErrorState } from '@/components/ErrorState'
import { ObjectLink } from '@/components/ObjectLink'
import { RelativeTime } from '@/components/RelativeTime'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { formatCompact, formatMs, formatNumber } from '@/lib/format'
import { routes } from '@/lib/routes'
import { STATS_QUERY_OPTS, useServerSort } from './useStatsQuery'

const SORTS: readonly ProcStatsSort[] = ['exec_count', 'total_ms', 'avg_ms', 'max_ms', 'cpu', 'reads', 'last_exec', 'name']

export function HotProcsGrid({ scanId }: { scanId: number }) {
  const sort = useServerSort<ProcStatsSort>('total_ms', SORTS)
  const q = $api.useQuery('get', '/api/scans/{scan_id}/stats/procs', { params: { path: scanPath(scanId), query: sort.query } }, STATS_QUERY_OPTS)
  const columns = useMemo<GridColumn<ProcStatsRow>[]>(
    () => [
      { id: 'name', header: 'Routine', minWidth: 280, sortable: true, cell: (r) => <ObjectLink id={r.object.id} db={r.object.db} schema={r.object.schema} kind={r.object.kind} name={r.object.name} showIcon className="text-[12.5px]" /> },
      { id: 'exec_count', header: 'Execs', width: 100, align: 'right', mono: true, sortable: true, cell: (r) => <span title={formatNumber(r.exec_count)}>{formatCompact(r.exec_count)}</span> },
      { id: 'total_ms', header: 'Total', width: 100, align: 'right', mono: true, sortable: true, cell: (r) => formatMs(r.total_ms) },
      { id: 'avg_ms', header: 'Avg', width: 100, align: 'right', mono: true, sortable: true, cell: (r) => formatMs(r.avg_ms) },
      { id: 'max_ms', header: 'Max', width: 100, align: 'right', mono: true, sortable: true, cell: (r) => formatMs(r.max_ms) },
      { id: 'cpu', header: 'CPU', width: 100, align: 'right', mono: true, sortable: true, cell: (r) => formatMs(r.total_cpu_ms) },
      { id: 'reads', header: 'Logical reads', width: 120, align: 'right', mono: true, sortable: true, cell: (r) => formatCompact(r.total_logical_reads) },
      { id: 'last_exec', header: 'Last exec', width: 120, sortable: true, cell: (r) => <RelativeTime value={r.last_exec_at} className="text-muted-foreground" /> },
      { id: 'cached', header: 'Cached since', width: 120, cell: (r) => <RelativeTime value={r.cached_since} className="text-muted-foreground" /> },
    ],
    [],
  )
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  return (
    <DataGrid
      aria-label="Procedure and function execution stats"
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
      emptyState="No cached execution stats — routines that have not run since the last restart do not appear in sys.dm_exec_*_stats."
      footer={q.data ? `${formatNumber(q.data.total)} routines with cached plans` : undefined}
    />
  )
}
