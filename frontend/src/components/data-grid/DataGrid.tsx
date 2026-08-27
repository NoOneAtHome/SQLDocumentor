/**
 * The single TanStack Table 9 wrapper used by every grid in the app.
 *
 * Columns are described with a small `GridColumn` spec (header, cell renderer, optional sort
 * value); sorting can be client-side (default) or controlled + manual for server-sorted lists.
 * Long lists are virtualised with @tanstack/react-virtual. Rows are laid out with CSS grid so
 * virtualised rows can be absolutely positioned without breaking column alignment.
 */
import {
  type RowData,
  type SortingState,
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import { type CSSProperties, type ReactNode, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
})

export type SortValue = string | number | boolean | null | undefined

export interface GridColumn<TData extends RowData> {
  id: string
  header: ReactNode
  cell: (row: TData) => ReactNode
  /** Provide to make the column sortable (client-side unless `manualSorting`). */
  sortValue?: (row: TData) => SortValue
  /** When `manualSorting`, allow sorting even without a `sortValue`. */
  sortable?: boolean
  width?: number | string
  minWidth?: number
  align?: 'left' | 'right' | 'center'
  mono?: boolean
  className?: string
  headerClassName?: string
  title?: string
}

export interface DataGridProps<TData extends RowData> {
  data: readonly TData[]
  columns: GridColumn<TData>[]
  rowKey: (row: TData, index: number) => string
  /** Controlled sorting (use with `manualSorting` for server-side sorts). */
  sorting?: SortingState
  onSortingChange?: (sorting: SortingState) => void
  manualSorting?: boolean
  defaultSorting?: SortingState
  onRowClick?: (row: TData, event: React.MouseEvent) => void
  /** Row becomes a navigable link target (Enter / click / middle-click). */
  rowHref?: (row: TData) => string | undefined
  isRowActive?: (row: TData) => boolean
  rowClassName?: (row: TData) => string | undefined
  loading?: boolean
  /** Background refetch — dims the body but keeps previous rows (keepPreviousData). */
  fetching?: boolean
  emptyState?: ReactNode
  className?: string
  /** Bounded height → internal scroll + virtualisation. */
  maxHeight?: number | string
  rowHeight?: number
  virtualize?: boolean
  dense?: boolean
  footer?: ReactNode
  'aria-label'?: string
}

const EMPTY: never[] = []

function compareValues(a: SortValue, b: SortValue): number {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b)
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
}

export function DataGrid<TData extends RowData>({
  data,
  columns,
  rowKey,
  sorting,
  onSortingChange,
  manualSorting = false,
  defaultSorting,
  onRowClick,
  rowHref,
  isRowActive,
  rowClassName,
  loading,
  fetching,
  emptyState,
  className,
  maxHeight,
  rowHeight,
  virtualize,
  dense,
  footer,
  'aria-label': ariaLabel,
}: DataGridProps<TData>) {
  const navigate = useNavigate()
  const helper = useMemo(() => createColumnHelper<typeof features, TData>(), [])
  const rowH = rowHeight ?? (dense ? 30 : 36)

  const tableColumns = useMemo(
    () =>
      helper.columns(
        columns.map((c) =>
          c.sortValue || (manualSorting && c.sortable)
            ? helper.accessor((row: TData) => (c.sortValue ? (c.sortValue(row) ?? null) : null), {
                id: c.id,
                header: () => c.header,
                cell: (ctx) => c.cell(ctx.row.original),
                enableSorting: true,
                sortFn: (a, b, columnId) => compareValues(a.getValue(columnId) as SortValue, b.getValue(columnId) as SortValue),
                sortDescFirst: false,
              })
            : helper.display({
                id: c.id,
                header: () => c.header,
                cell: (ctx) => c.cell(ctx.row.original),
                enableSorting: false,
              }),
        ),
      ),
    [columns, helper, manualSorting],
  )

  const table = useTable(
    {
      features,
      columns: tableColumns,
      data: (data as TData[]) ?? EMPTY,
      manualSorting,
      enableSortingRemoval: true,
      initialState: defaultSorting ? { sorting: defaultSorting } : undefined,
      ...(sorting !== undefined ? { state: { sorting } } : {}),
      // Only supplied for controlled sorting. TanStack merges options with a spread, so an explicit
      // `onSortingChange: undefined` would replace its default state updater and freeze client-side sorting.
      ...(onSortingChange
        ? {
            onSortingChange: (updater: SortingState | ((old: SortingState) => SortingState)) => {
              const next = typeof updater === 'function' ? updater(sorting ?? []) : updater
              onSortingChange(next)
            },
          }
        : {}),
    },
    (state) => ({ sorting: state.sorting }),
  )

  const rows = table.getRowModel().rows
  const scrollRef = useRef<HTMLDivElement>(null)
  const shouldVirtualize = (virtualize ?? rows.length > 60) && !!maxHeight
  const virtualizer = useVirtualizer({
    count: shouldVirtualize ? rows.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowH,
    overscan: 12,
    getItemKey: (i) => rowKey(rows[i]!.original, i),
  })

  const template = useMemo(
    () =>
      columns
        .map((c) =>
          typeof c.width === 'number'
            ? `${c.width}px`
            : typeof c.width === 'string'
              ? c.width
              : `minmax(${c.minWidth ?? 96}px, 1fr)`,
        )
        .join(' '),
    [columns],
  )

  const interactive = !!(onRowClick || rowHref)
  const cellPad = dense ? 'px-2.5' : 'px-3'

  const renderRow = (rowIndex: number, style?: CSSProperties) => {
    const row = rows[rowIndex]!
    const original = row.original
    const href = rowHref?.(original)
    const active = isRowActive?.(original)
    return (
      <div
        key={rowKey(original, rowIndex)}
        role="row"
        aria-selected={active || undefined}
        tabIndex={interactive ? 0 : undefined}
        data-index={rowIndex}
        ref={shouldVirtualize ? virtualizer.measureElement : undefined}
        style={{ gridTemplateColumns: template, height: rowH, ...style }}
        className={cn(
          'grid w-full items-center border-b border-border/70 text-[13px] last:border-b-0',
          interactive && 'cursor-pointer outline-none hover:bg-muted/60 focus-visible:bg-muted/60',
          active && 'bg-accent/60 hover:bg-accent/70',
          rowClassName?.(original),
        )}
        onClick={(e) => {
          if ((e.target as HTMLElement).closest('a,button,input,textarea,[data-no-row-click]')) return
          onRowClick?.(original, e)
          if (href) {
            if (e.metaKey || e.ctrlKey) window.open(href, '_blank')
            else navigate(href)
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && href) navigate(href)
        }}
      >
        {row.getAllCells().map((cell, i) => {
          const col = columns[i]!
          return (
            <div
              key={cell.id}
              role="cell"
              title={col.title}
              className={cn(
                'min-w-0 truncate py-0 leading-none',
                cellPad,
                col.align === 'right' && 'text-right',
                col.align === 'center' && 'text-center',
                col.mono && 'font-mono tnum text-[12.5px]',
                col.className,
              )}
            >
              <table.FlexRender cell={cell} />
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className={cn('flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card', className)}>
      <div
        ref={scrollRef}
        role="table"
        aria-label={ariaLabel}
        aria-busy={loading || fetching || undefined}
        className={cn('relative min-w-0 overflow-auto', fetching && 'opacity-60 transition-opacity')}
        style={{ maxHeight }}
      >
        <div role="rowgroup" className="sticky top-0 z-10 bg-card/95 backdrop-blur">
          {table.getHeaderGroups().map((hg) => (
            <div key={hg.id} role="row" className="grid border-b border-border" style={{ gridTemplateColumns: template }}>
              {hg.headers.map((header, i) => {
                const col = columns[i]!
                const canSort = header.column.getCanSort()
                const sorted = header.column.getIsSorted()
                const label = header.isPlaceholder ? null : (
                  <span className="truncate">
                    <table.FlexRender header={header} />
                  </span>
                )
                return (
                  <div
                    key={header.id}
                    role="columnheader"
                    aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}
                    className={cn(
                      'flex h-8 min-w-0 items-center text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase select-none',
                      cellPad,
                      col.align === 'right' && 'justify-end',
                      col.align === 'center' && 'justify-center',
                      col.headerClassName,
                    )}
                  >
                    {canSort ? (
                      // A real button so the sort is reachable from the keyboard (Tab, then Enter/Space), not only by mouse.
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className={cn(
                          '-mx-1 flex h-full max-w-full min-w-0 cursor-pointer items-center gap-1 rounded-sm px-1 outline-none hover:text-foreground focus-visible:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50',
                          sorted && 'text-foreground',
                        )}
                      >
                        {label}
                        <span aria-hidden="true" className={cn('shrink-0 [&_svg]:size-3', sorted ? 'text-foreground' : 'text-muted-foreground/50')}>
                          {sorted === 'asc' ? <ArrowUp /> : sorted === 'desc' ? <ArrowDown /> : <ChevronsUpDown />}
                        </span>
                      </button>
                    ) : (
                      label
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        <div role="rowgroup" className="relative" style={shouldVirtualize ? { height: virtualizer.getTotalSize() } : undefined}>
          {loading && rows.length === 0 ? (
            Array.from({ length: 6 }, (_, r) => (
              <div key={r} role="row" className="grid items-center border-b border-border/60" style={{ gridTemplateColumns: template, height: rowH }}>
                {columns.map((c) => (
                  <div key={c.id} role="cell" className={cellPad}>
                    <Skeleton className="h-3 w-3/4" style={{ opacity: 1 - r * 0.12 }} />
                  </div>
                ))}
              </div>
            ))
          ) : rows.length === 0 ? (
            <div role="row">
              <div role="cell" className="px-4 py-10 text-center text-[13px] text-muted-foreground">
                {emptyState ?? 'No rows'}
              </div>
            </div>
          ) : shouldVirtualize ? (
            virtualizer.getVirtualItems().map((item) =>
              renderRow(item.index, {
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${item.start}px)`,
              }),
            )
          ) : (
            rows.map((_, i) => renderRow(i))
          )}
        </div>
      </div>
      {footer && <div className="border-t border-border bg-muted/30 px-3 py-1.5 text-[12px] text-muted-foreground">{footer}</div>}
    </div>
  )
}
