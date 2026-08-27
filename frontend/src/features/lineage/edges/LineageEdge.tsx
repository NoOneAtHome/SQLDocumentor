import { BaseEdge, EdgeLabelRenderer, type EdgeProps, getBezierPath, getSmoothStepPath } from '@xyflow/react'
import { memo } from 'react'
import { cn } from '@/lib/utils'
import type { ColumnFlowEdge, LineageFlowEdge } from '../graph/to-flow'
import { confidenceColor, confidenceDash, edgeKindColor } from './edge-styles'

/** Object-level edge: smooth-step path coloured by kind; dashed when not resolved. */
export const LineageEdge = memo(function LineageEdge(props: EdgeProps<LineageFlowEdge>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, markerEnd } = props
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 10 })
  const color = edgeKindColor(data?.kind ?? 'catalog')
  const highlighted = data?.highlighted
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        interactionWidth={14}
        style={{
          stroke: color,
          strokeWidth: highlighted ? 2 : 1.25,
          strokeDasharray: data?.resolution && data.resolution !== 'resolved' ? '5 4' : undefined,
          opacity: data?.dimmed ? 0.18 : 1,
          transition: 'opacity 120ms, stroke-width 120ms',
        }}
      />
      {highlighted && data && (
        <EdgeLabelRenderer>
          <div
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            className="pointer-events-none absolute rounded-sm border border-border bg-card px-1 py-px font-mono text-[10px] text-muted-foreground shadow-sm"
          >
            {data.kind}
            {data.detail ? ` · ${data.detail}` : ''}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
})

/** Column-level edge: bezier, styled by confidence (exact solid / inferred dashed / unresolved dotted amber), `via` label. */
export const ColumnLineageEdge = memo(function ColumnLineageEdge(props: EdgeProps<ColumnFlowEdge>) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, markerEnd } = props
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition })
  const confidence = data?.confidence ?? 'exact'
  const color = confidenceColor(confidence)
  const highlighted = data?.highlighted
  const title = data ? `${data.sourceColumn} → ${data.targetColumn} · ${confidence} · ${data.transform}${data.via ? ` · via ${data.via}` : ''}${data.expression ? `\n${data.expression}` : ''}` : undefined
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} interactionWidth={12} style={{ stroke: color, strokeWidth: highlighted ? 2 : 1.25, strokeDasharray: confidenceDash(confidence), transition: 'stroke-width 120ms' }} />
      {data && (data.via || highlighted) && (
        <EdgeLabelRenderer>
          <div
            title={title}
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`, borderColor: color }}
            className={cn('pointer-events-auto absolute max-w-48 truncate rounded-sm border bg-card px-1 py-px font-mono text-[9.5px] leading-3.5 text-muted-foreground shadow-sm', highlighted && 'text-foreground')}
          >
            {data.via ? `via ${data.via}` : `${data.transform}${data.expression ? `: ${data.expression}` : ''}`}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
})
