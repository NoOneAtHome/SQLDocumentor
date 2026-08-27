import { useMemo } from 'react'
import type { Index, ObjectDetail } from '@/api/types'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { EmptyState } from '@/components/EmptyState'
import { RelativeTime } from '@/components/RelativeTime'
import { formatCompact, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ListTree } from 'lucide-react'

export function IndexesTab({ detail }: { detail: ObjectDetail }) {
  const columns = useMemo<GridColumn<Index>[]>(
    () => [
      {
        id: 'name',
        header: 'Index',
        minWidth: 240,
        sortValue: (i) => i.name ?? '',
        cell: (i) => (
          <span className="flex items-center gap-1.5 font-mono text-[12.5px]">
            <span className="truncate">{i.name}</span>
            {i.is_primary_key && <span className="rounded-sm bg-warning/10 px-1 text-[10px] text-warning">PK</span>}
            {i.is_unique && !i.is_primary_key && <span className="rounded-sm bg-info/10 px-1 text-[10px] text-info">unique</span>}
            {i.is_disabled && <span className="rounded-sm bg-destructive/10 px-1 text-[10px] text-destructive">disabled</span>}
            {i.is_unused && <span className="rounded-sm bg-warning/10 px-1 text-[10px] text-warning">unused</span>}
          </span>
        ),
      },
      { id: 'type', header: 'Type', width: 130, mono: true, sortValue: (i) => i.type_desc, cell: (i) => (i.type_desc ?? '').toLowerCase() },
      {
        id: 'keys',
        header: 'Key columns',
        minWidth: 200,
        cell: (i) => (
          <span className="truncate font-mono text-[12px]">
            {(i.key_columns ?? []).map((k) => `${k.name}${k.desc ? ' ↓' : ''}`).join(', ')}
            {(i.included_columns?.length ?? 0) > 0 && <span className="text-muted-foreground"> include ({i.included_columns?.join(', ')})</span>}
            {i.filter && <span className="text-muted-foreground"> where {i.filter}</span>}
          </span>
        ),
      },
      { id: 'seeks', header: 'Seeks', width: 90, align: 'right', mono: true, sortValue: (i) => i.usage?.seeks, cell: (i) => (i.usage ? formatCompact(i.usage.seeks) : '—') },
      { id: 'scans', header: 'Scans', width: 90, align: 'right', mono: true, sortValue: (i) => i.usage?.scans, cell: (i) => (i.usage ? formatCompact(i.usage.scans) : '—') },
      { id: 'lookups', header: 'Lookups', width: 90, align: 'right', mono: true, sortValue: (i) => i.usage?.lookups, cell: (i) => (i.usage ? formatCompact(i.usage.lookups) : '—') },
      { id: 'updates', header: 'Updates', width: 90, align: 'right', mono: true, sortValue: (i) => i.usage?.updates, cell: (i) => (i.usage ? <span className={cn(i.is_unused && i.usage.updates > 0 && 'text-warning')} title={formatNumber(i.usage.updates)}>{formatCompact(i.usage.updates)}</span> : '—') },
      { id: 'last', header: 'Last used', width: 120, sortValue: (i) => i.usage?.last_seek ?? i.usage?.last_scan, cell: (i) => <RelativeTime value={i.usage?.last_seek ?? i.usage?.last_scan ?? i.usage?.last_lookup} className="text-muted-foreground" /> },
    ],
    [],
  )
  const indexes = detail.indexes ?? []
  if (indexes.length === 0) return <div className="p-6"><EmptyState icon={<ListTree />} title="No indexes" description="This object has no indexes in the snapshot." compact /></div>
  return (
    <div className="space-y-3 p-6">
      <DataGrid aria-label="Indexes" data={indexes} columns={columns} rowKey={(i) => String(i.id)} defaultSorting={[{ id: 'name', desc: false }]} />
      <p className="text-[11.5px] text-muted-foreground">Usage counters are cumulative since the last SQL Server restart.</p>
    </div>
  )
}
