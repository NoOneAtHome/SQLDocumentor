import { useMemo } from 'react'
import { $api, scanPath } from '@/api/client'
import type { MissingIndexRow, MissingIndexSort } from '@/api/types'
import { CopyButton } from '@/components/CopyButton'
import { ErrorState } from '@/components/ErrorState'
import { ObjectLink } from '@/components/ObjectLink'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { formatCompact, formatNumber } from '@/lib/format'
import { routes } from '@/lib/routes'
import { STATS_QUERY_OPTS, useServerSort } from './useStatsQuery'

const SORTS: readonly MissingIndexSort[] = ['improvement', 'seeks', 'impact', 'cost', 'name']

export function MissingIndexesGrid({ scanId }: { scanId: number }) {
  const sort = useServerSort<MissingIndexSort>('improvement', SORTS)
  const q = $api.useQuery('get', '/api/scans/{scan_id}/stats/missing-indexes', { params: { path: scanPath(scanId), query: sort.query } }, STATS_QUERY_OPTS)
  const columns = useMemo<GridColumn<MissingIndexRow>[]>(
    () => [
      { id: 'improvement', header: 'Improvement', width: 120, align: 'right', mono: true, sortable: true, cell: (r) => <span title={r.improvement_measure != null ? formatNumber(Math.round(r.improvement_measure)) : undefined}>{formatCompact(r.improvement_measure)}</span> },
      { id: 'name', header: 'Table', minWidth: 220, sortable: true, cell: (r) => <ObjectLink id={r.object.id} db={r.object.db} schema={r.object.schema} kind={r.object.kind} name={r.object.name} showIcon className="text-[12.5px]" /> },
      { id: 'eq', header: 'Equality', minWidth: 160, mono: true, cell: (r) => r.equality_columns ?? <span className="text-muted-foreground">—</span> },
      { id: 'ineq', header: 'Inequality', minWidth: 140, mono: true, cell: (r) => r.inequality_columns ?? <span className="text-muted-foreground">—</span> },
      { id: 'incl', header: 'Included', minWidth: 180, mono: true, cell: (r) => r.included_columns ?? <span className="text-muted-foreground">—</span> },
      { id: 'seeks', header: 'Seeks', width: 80, align: 'right', mono: true, sortable: true, cell: (r) => formatCompact(r.user_seeks) },
      { id: 'impact', header: 'Impact', width: 80, align: 'right', mono: true, sortable: true, cell: (r) => (r.avg_impact != null ? `${Math.round(r.avg_impact)}%` : '—') },
      { id: 'cost', header: 'Avg cost', width: 90, align: 'right', mono: true, sortable: true, cell: (r) => (r.avg_cost != null ? r.avg_cost.toFixed(1) : '—') },
      { id: 'ddl', header: '', width: 60, align: 'right', cell: (r) => (r.suggested_ddl ? <span data-no-row-click><CopyButton value={r.suggested_ddl} label="Copy CREATE INDEX" /></span> : null) },
    ],
    [],
  )
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  return (
    <DataGrid
      aria-label="Missing index suggestions"
      data={q.data?.items ?? []}
      columns={columns}
      rowKey={(r) => String(r.id)}
      loading={q.isPending}
      fetching={q.isFetching && !q.isPending}
      manualSorting
      sorting={sort.sorting}
      onSortingChange={sort.onSortingChange}
      rowHref={(r) => routes.object(scanId, r.object, 'stats')}
      maxHeight="calc(100vh - 220px)"
      emptyState="No missing-index suggestions in this snapshot."
      footer={q.data ? `${formatNumber(q.data.total)} suggestions · improvement = avg cost × avg impact × (seeks + scans)` : undefined}
    />
  )
}
