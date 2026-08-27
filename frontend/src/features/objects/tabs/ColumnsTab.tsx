import { ArrowDownRight, ArrowUpRight, KeyRound, Link2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import type { Column, ObjectDetail } from '@/api/types'
import { ObjectLink } from '@/components/ObjectLink'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { Input } from '@/components/ui/input'
import { DescriptionEditor } from '@/features/annotations/DescriptionEditor'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'

export function ColumnsTab({ scanId, detail, connection }: { scanId: number; detail: ObjectDetail; connection: string }) {
  const s = detail.summary
  const [filter, setFilter] = useState('')
  const allColumns = useMemo(() => detail.columns ?? [], [detail.columns])
  const rows = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return f ? allColumns.filter((c) => c.name.toLowerCase().includes(f) || (c.type_display ?? '').toLowerCase().includes(f)) : allColumns
  }, [allColumns, filter])

  const columns = useMemo<GridColumn<Column>[]>(
    () => [
      { id: 'ordinal', header: '#', width: 44, align: 'right', mono: true, sortValue: (c) => c.ordinal, cell: (c) => <span className="text-muted-foreground">{c.ordinal}</span> },
      {
        id: 'name',
        header: 'Column',
        minWidth: 200,
        sortValue: (c) => c.name,
        cell: (c) => (
          <span className="flex items-center gap-1.5 font-mono text-[12.5px]">
            {c.in_primary_key && <KeyRound className="size-3 text-warning" aria-label="Primary key" />}
            {c.fk_to && <Link2 className="size-3 text-obj-table" aria-label="Foreign key" />}
            <span className="truncate">{c.name}</span>
            {c.column_kind !== 'column' && <span className="rounded-sm bg-muted px-1 text-[10px] text-muted-foreground">{c.column_kind}</span>}
          </span>
        ),
      },
      { id: 'type', header: 'Type', width: 150, mono: true, sortValue: (c) => c.type_display, cell: (c) => c.type_display ?? '' },
      {
        id: 'flags',
        header: 'Attributes',
        width: 220,
        cell: (c) => (
          <span className="flex flex-wrap gap-1 font-mono text-[10.5px]">
            <span className={cn('rounded-sm px-1', c.is_nullable ? 'bg-muted text-muted-foreground' : 'bg-foreground/8 text-foreground/80')}>{c.is_nullable ? 'NULL' : 'NOT NULL'}</span>
            {c.is_identity && <span className="rounded-sm bg-info/10 px-1 text-info">identity</span>}
            {c.is_computed && (
              <span className="rounded-sm bg-obj-function/10 px-1 text-obj-function" title={c.computed_definition ?? ''}>
                computed
              </span>
            )}
            {c.default_definition && (
              <span className="truncate rounded-sm bg-muted px-1 text-muted-foreground" title={c.default_definition}>
                default {c.default_definition}
              </span>
            )}
          </span>
        ),
      },
      {
        id: 'fk',
        header: 'References',
        width: 200,
        cell: (c) =>
          c.fk_to ? (
            <ObjectLink id={c.fk_to.object_id} db={s.db} schema={c.fk_to.schema} kind="table" name={c.fk_to.name} className="text-[12px]">
              <span className="text-muted-foreground">{c.fk_to.schema}.</span>
              {c.fk_to.name}
              <span className="text-muted-foreground">.{c.fk_to.column}</span>
            </ObjectLink>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: 'lineage',
        header: 'Lineage',
        width: 110,
        align: 'right',
        sortValue: (c) => c.lineage.upstream + c.lineage.downstream,
        cell: (c) =>
          c.lineage.upstream + c.lineage.downstream > 0 ? (
            <Link to={routes.lineage(scanId, { ...s, col: c.name, level: 'column' })} className="inline-flex items-center gap-1.5 font-mono text-[11.5px] text-primary tnum hover:underline" data-no-row-click>
              <span className="inline-flex items-center gap-0.5">
                <ArrowUpRight className="size-3" />
                {c.lineage.upstream}
              </span>
              <span className="inline-flex items-center gap-0.5">
                <ArrowDownRight className="size-3" />
                {c.lineage.downstream}
              </span>
            </Link>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        id: 'description',
        header: 'Description',
        minWidth: 260,
        cell: (c) => (
          <div data-no-row-click className="min-w-0">
            <DescriptionEditor
              scanId={scanId}
              connection={connection}
              target={s}
              column={c.name}
              value={detail.column_annotations?.[c.name]?.description ?? null}
              fallback={c.ms_description}
              inline
            />
          </div>
        ),
      },
    ],
    [s, scanId, connection, detail.column_annotations],
  )

  return (
    <div className="space-y-3 p-6">
      <div className="flex items-center gap-2">
        <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter columns…" className="h-7 w-64 text-[12.5px]" />
        <span className="text-[12px] text-muted-foreground">
          {rows.length} of {allColumns.length}
        </span>
      </div>
      <DataGrid aria-label="Columns" data={rows} columns={columns} rowKey={(c) => String(c.id)} defaultSorting={[{ id: 'ordinal', desc: false }]} emptyState="No columns" maxHeight="calc(100vh - 260px)" />
    </div>
  )
}
