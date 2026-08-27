import { Handle, type NodeProps, Position } from '@xyflow/react'
import { TriangleAlert } from 'lucide-react'
import { memo } from 'react'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { KIND_COLOR, KIND_LABEL } from '@/lib/constants'
import { formatCompact } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useLineageActions } from '../actions-context'
import type { ObjectFlowNode } from '../graph/to-flow'
import { ExpandPill } from './ExpandPill'

function stat(node: ObjectFlowNode['data']['node']): string | null {
  if (node.row_count != null) return `${formatCompact(node.row_count)} rows`
  if (node.exec_count != null) return `${formatCompact(node.exec_count)} execs`
  return null
}

/** 240×64 object card: kind accent strip, icon + schema.name, compact stat, scope/issue badges, expand pills. */
export const ObjectNode = memo(function ObjectNode({ id, data, selected }: NodeProps<ObjectFlowNode>) {
  const actions = useLineageActions()
  const n = data.node
  const s = stat(n)
  return (
    <div
      data-kind-color={KIND_COLOR[n.kind]}
      className={cn(
        'relative h-16 w-60 rounded-md border bg-card text-card-foreground transition-[box-shadow,border-color] duration-150',
        n.scope === 'cascaded' && 'border-dashed',
        n.scope === 'external' && 'border-dotted border-muted-foreground/60 bg-muted/40',
        data.isFocus ? 'border-primary/60 shadow-[0_0_0_3px_color-mix(in_oklch,var(--primary)_18%,transparent)]' : 'border-border hover:border-foreground/30',
        selected && 'border-primary ring-2 ring-primary/40',
      )}
    >
      <Handle type="target" position={Position.Left} className="is-port" isConnectable={false} />
      <Handle type="source" position={Position.Right} className="is-port" isConnectable={false} />
      <div className={cn('absolute inset-y-0 left-0 w-1 rounded-l-[5px] bg-(--kind)', n.scope === 'external' && 'opacity-50')} />
      <div className="flex h-full min-w-0 flex-col justify-center gap-0.5 pr-2.5 pl-3.5">
        <div className="flex min-w-0 items-center gap-1.5">
          <ObjectTypeIcon kind={n.kind} className="size-3.5" />
          <span className="min-w-0 truncate font-mono text-[12px] leading-4 font-medium" title={`${n.schema ?? ''}.${n.name}`}>
            {n.schema && <span className="text-muted-foreground">{n.schema}.</span>}
            {n.name}
          </span>
          {n.has_lineage_issues && <TriangleAlert className="size-3 shrink-0 text-warning" aria-label="Lineage issues" />}
        </div>
        <div className="flex min-w-0 items-center gap-1.5 text-[10.5px] leading-3.5 text-muted-foreground">
          <span className="truncate">{KIND_LABEL[n.kind]}</span>
          {s && (
            <>
              <span className="text-border">·</span>
              <span className="font-mono tnum">{s}</span>
            </>
          )}
          {n.scope !== 'in_scope' && (
            <span className={cn('ml-auto rounded-sm border px-1 text-[9.5px] leading-3.5', n.scope === 'cascaded' ? 'border-dashed' : 'border-dotted')}>{n.scope}</span>
          )}
        </div>
      </div>
      <ExpandPill side="left" count={data.more.upstream} expanded={data.expanded.up} loading={data.loading.up} onClick={() => (data.expanded.up ? actions.collapse(id, 'up') : actions.expand(id, 'up'))} />
      <ExpandPill side="right" count={data.more.downstream} expanded={data.expanded.down} loading={data.loading.down} onClick={() => (data.expanded.down ? actions.collapse(id, 'down') : actions.expand(id, 'down'))} />
    </div>
  )
})
