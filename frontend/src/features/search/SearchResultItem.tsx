import { Columns3, CornerDownLeft } from 'lucide-react'
import type { ObjectSummary } from '@/api/types'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { KIND_LABEL } from '@/lib/constants'
import { Kbd } from '@/components/ui/kbd'

export function ObjectResult({ object, snippet }: { object: ObjectSummary; snippet?: string }) {
  return (
    <>
      <ObjectTypeIcon kind={object.kind} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-mono text-[12.5px]">
          <span className="text-muted-foreground">{object.schema}.</span>
          {object.name}
        </span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {KIND_LABEL[object.kind]}
          {object.scope !== 'in_scope' && ` · ${object.scope}`}
          {snippet && object.description ? ` · ${object.description}` : ''}
        </span>
      </span>
      <Kbd className="opacity-0 group-data-selected/command-item:opacity-100">
        <CornerDownLeft className="size-3" />
      </Kbd>
    </>
  )
}

export function ColumnResult({ object, column, dataType }: { object: ObjectSummary; column: string; dataType: string }) {
  return (
    <>
      <Columns3 className="text-muted-foreground" />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-mono text-[12.5px]">
          <span className="text-muted-foreground">
            {object.schema}.{object.name}.
          </span>
          {column}
        </span>
        <span className="block truncate font-mono text-[11px] text-muted-foreground">{dataType}</span>
      </span>
    </>
  )
}
