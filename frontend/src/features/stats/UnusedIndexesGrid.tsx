import { useMemo, useState } from 'react'
import { $api, scanPath } from '@/api/client'
import type { IndexStatsRow, IndexStatsSort } from '@/api/types'
import { ErrorState } from '@/components/ErrorState'
import { ObjectLink } from '@/components/ObjectLink'
import { RelativeTime } from '@/components/RelativeTime'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { formatCompact, formatNumber } from '@/lib/format'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'
import { STATS_QUERY_OPTS, useServerSort } from './useStatsQuery'

const SORTS: readonly IndexStatsSort[] = ['updates', 'seeks', 'scans', 'lookups', 'name', 'table']

export function UnusedIndexesGrid({ scanId }: { scanId: number }) {
  const [unusedOnly, setUnusedOnly] = useState(true)
  const sort = useServerSort<IndexStatsSort>('updates', SORTS)
  const q = $api.useQuery('get', '/api/scans/{scan_id}/stats/indexes', { params: { path: scanPath(scanId), query: { ...sort.query, unused: unusedOnly } } }, STATS_QUERY_OPTS)
  const columns = useMemo<GridColumn<IndexStatsRow>[]>(
    () => [
      {
        id: 'name',
        header: 'Index',
        minWidth: 300,
        sortable: true,
        cell: (r) => (
          <span className="flex min-w-0 flex-col leading-tight">
            <span className="truncate font-mono text-[12.5px]">
              {r.index_name ?? `index #${r.index_id}`}
              {r.is_unused && <span className="ml-1.5 rounded-sm bg-warning/10 px-1 text-[10px] text-warning">unused</span>}
            </span>
            <ObjectLink id={r.object.id} db={r.object.db} schema={r.object.schema} kind={r.object.kind} name={r.object.name} className="text-[11px] text-muted-foreground" />
          </span>
        ),
      },
      { id: 'table', header: 'Table', width: 160, sortable: true, cell: (r) => <span className="truncate font-mono text-[12px]">{r.object.name}</span> },
      { id: 'type', header: 'Type', width: 120, cell: (r) => <span className="font-mono text-[11px] text-muted-foreground">{(r.type_desc ?? '').toLowerCase()}{r.is_unique ? ' · unique' : ''}</span> },
      {
        id: 'keys',
        header: 'Columns',
        minWidth: 200,
        cell: (r) => (
          <span className="truncate font-mono text-[12px]">
            {(r.key_columns ?? []).join(', ')}
            {(r.included_columns?.length ?? 0) > 0 ? <span className="text-muted-foreground"> +{r.included_columns?.length} incl.</span> : null}
          </span>
        ),
      },
      { id: 'seeks', header: 'Seeks', width: 90, align: 'right', mono: true, sortable: true, cell: (r) => formatCompact(r.seeks) },
      { id: 'scans', header: 'Scans', width: 90, align: 'right', mono: true, sortable: true, cell: (r) => formatCompact(r.scans) },
      { id: 'lookups', header: 'Lookups', width: 90, align: 'right', mono: true, sortable: true, cell: (r) => formatCompact(r.lookups) },
      { id: 'updates', header: 'Updates', width: 100, align: 'right', mono: true, sortable: true, cell: (r) => <span className={cn(r.is_unused && r.updates > 0 && 'text-warning')} title={`${formatNumber(r.updates)} writes maintained for no reads`}>{formatCompact(r.updates)}</span> },
      { id: 'last', header: 'Last used', width: 120, cell: (r) => <RelativeTime value={r.last_seek ?? r.last_scan ?? r.last_lookup} className="text-muted-foreground" /> },
    ],
    [],
  )
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  return (
    <div className="space-y-3">
      <label className="flex w-fit items-center gap-2 text-[12.5px]">
        <Switch checked={unusedOnly} onCheckedChange={setUnusedOnly} />
        <Label>Unused only (no seeks, scans or lookups since server start)</Label>
      </label>
      <DataGrid
        aria-label="Index usage"
        data={q.data?.items ?? []}
        columns={columns}
        rowKey={(r) => `${r.object.id}-${r.index_id}`}
        loading={q.isPending}
        fetching={q.isFetching && !q.isPending}
        manualSorting
        sorting={sort.sorting}
        onSortingChange={sort.onSortingChange}
        rowHref={(r) => routes.object(scanId, r.object, 'indexes')}
        rowHeight={44}
        maxHeight="calc(100vh - 260px)"
        emptyState="No unused indexes — nice."
        footer={q.data ? `${formatNumber(q.data.total)} indexes` : undefined}
      />
    </div>
  )
}
