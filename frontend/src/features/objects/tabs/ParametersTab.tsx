import { useMemo } from 'react'
import { Braces } from 'lucide-react'
import type { ObjectDetail, Parameter } from '@/api/types'
import { DataGrid, type GridColumn } from '@/components/data-grid/DataGrid'
import { EmptyState } from '@/components/EmptyState'

export function ParametersTab({ detail }: { detail: ObjectDetail }) {
  const parameters = detail.parameters ?? []
  const columns = useMemo<GridColumn<Parameter>[]>(
    () => [
      { id: 'ordinal', header: '#', width: 44, align: 'right', mono: true, sortValue: (p) => p.parameter_id, cell: (p) => <span className="text-muted-foreground">{p.is_return_value ? '↩' : p.parameter_id}</span> },
      { id: 'name', header: 'Parameter', minWidth: 200, mono: true, cell: (p) => (p.is_return_value ? <span className="text-muted-foreground">RETURNS</span> : p.name) },
      { id: 'type', header: 'Type', width: 160, mono: true, cell: (p) => p.type_display ?? '' },
      {
        id: 'flags',
        header: 'Attributes',
        width: 220,
        cell: (p) => (
          <span className="flex gap-1 font-mono text-[10.5px]">
            {p.is_output && <span className="rounded-sm bg-info/10 px-1 text-info">OUTPUT</span>}
            {p.is_readonly && <span className="rounded-sm bg-muted px-1 text-muted-foreground">READONLY</span>}
            {p.is_table_type && <span className="rounded-sm bg-muted px-1 text-muted-foreground">table type</span>}
            {p.has_default_value && <span className="rounded-sm bg-muted px-1 text-muted-foreground">default {p.default_value ?? ''}</span>}
          </span>
        ),
      },
      { id: 'description', header: 'Description', minWidth: 240, cell: (p) => <span className="truncate text-muted-foreground">{p.description ?? ''}</span> },
    ],
    [],
  )
  if (parameters.length === 0) return <div className="p-6"><EmptyState icon={<Braces />} title="No parameters" compact /></div>
  return (
    <div className="p-6">
      <DataGrid aria-label="Parameters" data={parameters} columns={columns} rowKey={(p) => `${p.id}-${p.parameter_id}`} />
    </div>
  )
}
