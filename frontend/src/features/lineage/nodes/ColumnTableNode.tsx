import { Handle, type NodeProps, Position, useUpdateNodeInternals } from '@xyflow/react'
import { TriangleAlert } from 'lucide-react'
import { memo, useEffect } from 'react'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { KIND_COLOR } from '@/lib/constants'
import { cn } from '@/lib/utils'
import { useLineageActions } from '../actions-context'
import { COLUMN_FOOTER_H, COLUMN_HEADER_H, COLUMN_NODE_WIDTH, COLUMN_ROW_H, columnHandleTop, handleId } from '../graph/sizes'
import type { ColumnFlowNode } from '../graph/to-flow'
import { ExpandPill } from './ExpandPill'

/**
 * Column-level table node: header + one 24px row per column with `in:`/`out:` Handles whose CSS
 * `top` equals the ELK port y (see sizes.ts) — no measure-then-layout round trip.
 */
export const ColumnTableNode = memo(function ColumnTableNode({ id, data, selected }: NodeProps<ColumnFlowNode>) {
  const actions = useLineageActions()
  const updateNodeInternals = useUpdateNodeInternals()
  const n = data.node
  const rowCount = data.columns.length
  useEffect(() => {
    if (rowCount > 0) updateNodeInternals(id)
  }, [id, rowCount, updateNodeInternals])

  return (
    <div
      data-kind-color={KIND_COLOR[n.kind]}
      style={{ width: COLUMN_NODE_WIDTH }}
      className={cn(
        'relative rounded-md border bg-card text-card-foreground',
        n.scope === 'cascaded' && 'border-dashed',
        n.scope === 'external' && 'border-dotted border-muted-foreground/60 bg-muted/40',
        data.isFocus ? 'border-primary/60 shadow-[0_0_0_3px_color-mix(in_oklch,var(--primary)_18%,transparent)]' : 'border-border',
        selected && 'border-primary ring-2 ring-primary/40',
      )}
    >
      <div className="absolute inset-y-0 left-0 w-1 rounded-l-[5px] bg-(--kind)" />
      <div style={{ height: COLUMN_HEADER_H }} className="flex min-w-0 items-center gap-1.5 border-b border-border pr-2.5 pl-3.5">
        <ObjectTypeIcon kind={n.kind} className="size-3.5" />
        <span className="min-w-0 truncate font-mono text-[12px] font-medium" title={`${n.schema ?? ''}.${n.name}`}>
          {n.schema && <span className="text-muted-foreground">{n.schema}.</span>}
          {n.name}
        </span>
        {n.has_lineage_issues && <TriangleAlert className="size-3 shrink-0 text-warning" />}
        <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground tnum">
          {n.columns?.length ?? 0}/{n.column_count_total}
        </span>
      </div>

      {data.columns.map((c) => {
        const isFocusCol = data.focusColumn != null && c.name === data.focusColumn
        return (
          <div
            key={c.name}
            style={{ height: COLUMN_ROW_H }}
            className={cn(
              'flex min-w-0 items-center gap-2 px-3 font-mono text-[11.5px] leading-none',
              !c.participating && 'text-muted-foreground/60',
              isFocusCol && 'bg-primary/10',
              c.participating && 'hover:bg-muted/60',
            )}
            onClick={() => c.participating && actions.selectColumn(id, c.name)}
            title={c.data_type ?? c.name}
          >
            <span className={cn('size-1.5 shrink-0 rounded-full', c.participating ? 'bg-(--kind)' : 'bg-border')} />
            <span className="min-w-0 flex-1 truncate">{c.name}</span>
            {c.data_type && <span className="shrink-0 truncate text-[10px] text-muted-foreground/70">{c.data_type}</span>}
          </div>
        )
      })}

      {data.columns.map((c, i) => (
        <span key={`h-${c.name}`} className="contents">
          <Handle type="target" position={Position.Left} id={handleId('in', c.name)} style={{ top: columnHandleTop(i) }} className={cn('is-port', c.participating && 'is-active')} isConnectable={false} />
          <Handle type="source" position={Position.Right} id={handleId('out', c.name)} style={{ top: columnHandleTop(i) }} className={cn('is-port', c.participating && 'is-active')} isConnectable={false} />
        </span>
      ))}

      {data.hasMoreColumns && (
        <button
          type="button"
          style={{ height: COLUMN_FOOTER_H }}
          className="nodrag flex w-full items-center justify-center border-t border-border text-[10.5px] text-muted-foreground hover:bg-muted/60 hover:text-foreground"
          onClick={(e) => {
            e.stopPropagation()
            void actions.toggleShowAll(id)
          }}
        >
          {data.showAll ? 'show participating only' : `show all ${n.column_count_total} columns`}
        </button>
      )}

      <ExpandPill side="left" count={n.more.upstream} expanded={data.expanded.up} loading={data.loading.up} onClick={() => (data.expanded.up ? actions.collapse(id, 'up') : actions.expand(id, 'up'))} className="top-5" />
      <ExpandPill side="right" count={n.more.downstream} expanded={data.expanded.down} loading={data.loading.down} onClick={() => (data.expanded.down ? actions.collapse(id, 'down') : actions.expand(id, 'down'))} className="top-5" />
    </div>
  )
})
