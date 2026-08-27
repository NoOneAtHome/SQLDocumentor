import { Trash2 } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import type { ScanSummary } from '@/api/types'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { RelativeTime } from '@/components/RelativeTime'
import { Button } from '@/components/ui/button'
import { formatDurationMs, formatNumber } from '@/lib/format'
import { routes } from '@/lib/routes'
import { cn, errorMessage } from '@/lib/utils'
import { useDeleteScan } from './useScanProgress'

export function ScanHistoryTable({ scans, loading, activeId }: { scans: ScanSummary[]; loading?: boolean; activeId?: number | null }) {
  const del = useDeleteScan()
  const columns = useMemo<GridColumn<ScanSummary>[]>(
    () => [
      {
        id: 'id',
        header: 'Scan',
        width: 90,
        mono: true,
        sortValue: (s) => s.id,
        cell: (s) =>
          s.status === 'succeeded' ? (
            <Link to={routes.scan(s.id)} className="text-primary underline-offset-2 hover:underline">
              #{s.id}
            </Link>
          ) : (
            <span>#{s.id}</span>
          ),
      },
      {
        id: 'status',
        header: 'Status',
        width: 110,
        sortValue: (s) => s.status,
        cell: (s) => (
          <span
            className={cn(
              'rounded-sm px-1.5 py-0.5 text-[11px] font-medium',
              s.status === 'running' && 'bg-info/10 text-info',
              s.status === 'succeeded' && 'bg-success/10 text-success',
              s.status === 'failed' && 'bg-destructive/10 text-destructive',
              s.status === 'cancelled' && 'bg-muted text-muted-foreground',
            )}
          >
            {s.status}
          </span>
        ),
      },
      { id: 'started', header: 'Started', width: 140, sortValue: (s) => s.started_at, cell: (s) => <RelativeTime value={s.started_at} /> },
      { id: 'duration', header: 'Duration', width: 100, align: 'right', mono: true, sortValue: (s) => s.duration_ms, cell: (s) => formatDurationMs(s.duration_ms) },
      { id: 'tables', header: 'Tables', width: 80, align: 'right', mono: true, sortValue: (s) => s.counts?.tables, cell: (s) => formatNumber(s.counts?.tables) },
      { id: 'views', header: 'Views', width: 80, align: 'right', mono: true, sortValue: (s) => s.counts?.views, cell: (s) => formatNumber(s.counts?.views) },
      { id: 'routines', header: 'Routines', width: 90, align: 'right', mono: true, sortValue: (s) => (s.counts ? s.counts.procedures + s.counts.functions : null), cell: (s) => formatNumber(s.counts ? s.counts.procedures + s.counts.functions : null) },
      { id: 'edges', header: 'Col. edges', width: 100, align: 'right', mono: true, sortValue: (s) => s.counts?.edges_column, cell: (s) => formatNumber(s.counts?.edges_column) },
      { id: 'issues', header: 'Issues', width: 80, align: 'right', mono: true, sortValue: (s) => s.counts?.lineage_issues, cell: (s) => <span className={cn((s.counts?.lineage_issues ?? 0) > 0 && 'text-warning')}>{formatNumber(s.counts?.lineage_issues)}</span> },
      {
        id: 'options',
        header: 'Options',
        minWidth: 140,
        cell: (s) => (
          <span className="text-[12px] text-muted-foreground">
            {[s.options?.collect_stats && 'stats', s.options?.parse_lineage && 'lineage'].filter(Boolean).join(' · ') || 'catalog only'}
            {s.error && <span className="ml-2 text-destructive">{s.error}</span>}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '',
        width: 44,
        align: 'right',
        cell: (s) =>
          s.status !== 'running' ? (
            <Button
              variant="ghost"
              size="icon-xs"
              className="text-muted-foreground hover:text-destructive"
              aria-label={`Delete scan ${s.id}`}
              data-no-row-click
              onClick={() =>
                del.mutate(
                  { params: { path: { scan_id: s.id } } },
                  { onSuccess: () => toast.success(`Scan #${s.id} deleted`), onError: (e) => toast.error('Could not delete', { description: errorMessage(e) }) },
                )
              }
            >
              <Trash2 />
            </Button>
          ) : null,
      },
    ],
    [del],
  )

  return (
    <DataGrid
      aria-label="Scan history"
      data={scans}
      columns={columns}
      rowKey={(s) => String(s.id)}
      loading={loading}
      defaultSorting={[{ id: 'id', desc: true }]}
      isRowActive={(s) => s.id === activeId}
      rowHref={(s) => (s.status === 'succeeded' ? routes.scan(s.id) : undefined)}
      emptyState="No scans yet — start one above."
      dense
    />
  )
}
