import { ChartBar, Lightbulb } from 'lucide-react'
import { useMemo } from 'react'
import type { ExecStats, Index, MissingIndex, ObjectDetail, TableStats } from '@/api/types'
import { CodeBlock } from '@/components/CodeBlock'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { EmptyState } from '@/components/EmptyState'
import { KeyValueGrid } from '@/components/KeyValueGrid'
import { StatCard } from '@/components/StatCard'
import { formatCompact, formatDateTime, formatKb, formatMs, formatNumber, formatRows } from '@/lib/format'

function isTableStats(s: ObjectDetail['stats']): s is TableStats {
  return s?.kind === 'table'
}
function isExecStats(s: ObjectDetail['stats']): s is ExecStats {
  return s?.kind === 'exec'
}

export function StatsTab({ detail }: { detail: ObjectDetail }) {
  const stats = detail.stats
  const indexCols = useMemo<GridColumn<Index>[]>(
    () => [
      { id: 'name', header: 'Index', minWidth: 220, mono: true, sortValue: (i) => i.name ?? '', cell: (i) => i.name ?? '' },
      { id: 'seeks', header: 'Seeks', width: 90, align: 'right', mono: true, sortValue: (i) => i.usage?.seeks, cell: (i) => formatCompact(i.usage?.seeks) },
      { id: 'scans', header: 'Scans', width: 90, align: 'right', mono: true, sortValue: (i) => i.usage?.scans, cell: (i) => formatCompact(i.usage?.scans) },
      { id: 'lookups', header: 'Lookups', width: 90, align: 'right', mono: true, sortValue: (i) => i.usage?.lookups, cell: (i) => formatCompact(i.usage?.lookups) },
      { id: 'updates', header: 'Updates', width: 90, align: 'right', mono: true, sortValue: (i) => i.usage?.updates, cell: (i) => formatCompact(i.usage?.updates) },
      { id: 'unused', header: '', width: 90, cell: (i) => (i.is_unused ? <span className="rounded-sm bg-warning/10 px-1 font-mono text-[10.5px] text-warning">unused</span> : null) },
    ],
    [],
  )
  const miCols = useMemo<GridColumn<MissingIndex>[]>(
    () => [
      { id: 'impr', header: 'Improvement', width: 120, align: 'right', mono: true, sortValue: (m) => m.improvement_measure, cell: (m) => formatCompact(m.improvement_measure) },
      { id: 'eq', header: 'Equality', minWidth: 160, mono: true, cell: (m) => m.equality_columns ?? '—' },
      { id: 'ineq', header: 'Inequality', minWidth: 140, mono: true, cell: (m) => m.inequality_columns ?? '—' },
      { id: 'incl', header: 'Included', minWidth: 160, mono: true, cell: (m) => m.included_columns ?? '—' },
      { id: 'seeks', header: 'Seeks', width: 80, align: 'right', mono: true, cell: (m) => formatCompact(m.user_seeks) },
      { id: 'impact', header: 'Impact', width: 80, align: 'right', mono: true, cell: (m) => (m.avg_impact != null ? `${Math.round(m.avg_impact)}%` : '—') },
    ],
    [],
  )

  const indexes = detail.indexes ?? []
  const missing = detail.missing_indexes ?? []
  if (!stats && missing.length === 0)
    return (
      <div className="p-6">
        <EmptyState icon={<ChartBar />} title="No stats collected" description="Stats were disabled for this scan or the login lacks VIEW DATABASE STATE." compact />
      </div>
    )

  return (
    <div className="space-y-6 p-6">
      {isTableStats(stats) && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Rows" value={formatCompact(stats.row_count)} hint={formatRows(stats.row_count)} />
            <StatCard label="Data" value={formatKb(stats.data_kb)} hint={`${formatNumber(stats.data_kb)} KB`} />
            <StatCard label="Index" value={formatKb(stats.index_kb)} hint={`${formatNumber(stats.index_kb)} KB`} />
            <StatCard label="Reserved" value={formatKb(stats.reserved_kb)} hint={`${stats.partition_count ?? '—'} partition${stats.partition_count === 1 ? '' : 's'}`} />
          </div>
          <KeyValueGrid
            columns={2}
            items={[
              { label: 'Storage', value: stats.is_heap ? 'Heap' : 'Clustered' },
              { label: 'Compression', value: stats.compression ?? '—' },
              { label: 'Partitions', value: stats.partition_count ?? '—', mono: true },
              { label: 'As of', value: formatDateTime(stats.stats_as_of) },
            ]}
          />
          {indexes.length > 0 && (
            <section>
              <h2 className="mb-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Index usage</h2>
              <DataGrid aria-label="Index usage" data={indexes} columns={indexCols} rowKey={(i) => String(i.id)} defaultSorting={[{ id: 'seeks', desc: true }]} dense />
            </section>
          )}
        </>
      )}
      {isExecStats(stats) && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Executions" value={formatCompact(stats.exec_count)} hint={formatNumber(stats.exec_count)} />
            <StatCard label="Avg elapsed" value={formatMs(stats.avg_ms)} hint={`min ${formatMs(stats.min_ms)} · max ${formatMs(stats.max_ms)}`} />
            <StatCard label="Total elapsed" value={formatMs(stats.total_ms)} hint={`cpu ${formatMs(stats.total_cpu_ms)}`} />
            <StatCard label="Last executed" value={<span className="text-[15px]">{formatDateTime(stats.last_exec_at)}</span>} hint={`cached since ${formatDateTime(stats.cached_since)}`} />
          </div>
          <p className="text-[11.5px] text-muted-foreground">Counters from sys.dm_exec_*_stats, cumulative since the plan was cached{stats.since_server_start ? ` (server start ${formatDateTime(stats.since_server_start)})` : ''}.</p>
        </>
      )}
      {missing.length > 0 && (
        <section className="space-y-3">
          <h2 className="flex items-center gap-1.5 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">
            <Lightbulb className="size-3.5 text-warning" /> Missing index suggestions
          </h2>
          <DataGrid aria-label="Missing indexes" data={missing} columns={miCols} rowKey={(m) => String(m.id)} defaultSorting={[{ id: 'impr', desc: true }]} dense />
          {missing.map((m) => (m.suggested_ddl ? <CodeBlock key={m.id} code={m.suggested_ddl} plain toolbar /> : null))}
        </section>
      )}
    </div>
  )
}
