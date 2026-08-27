import type { Edge, Node } from '@xyflow/react'
import type {
  ColumnLineageEdge,
  ColumnLineageNode,
  Confidence,
  EdgeKind,
  LineageEdge,
  LineageMore,
  LineageNode,
  Resolution,
  Transform,
} from '@/api/types'
import { CONFIDENCE_RANK } from '@/lib/constants'
import { type BaseEdge, type BaseNode, type GraphState, expansionId, isExpanded, visibleEdges, visibleNodes } from './graph-state'
import { OBJECT_NODE_HEIGHT, OBJECT_NODE_WIDTH, columnNodeHeight, COLUMN_NODE_WIDTH, handleId } from './sizes'

export type Positions = ReadonlyMap<string, { x: number; y: number }>

/** Per-direction expand-pill state shared by object and column-table nodes. */
export type PillState = {
  expanded: { up: boolean; down: boolean }
  loading: { up: boolean; down: boolean }
}

function pillState<N extends BaseNode, E extends BaseEdge>(state: GraphState<N, E>, id: string, loading: ReadonlySet<string>): PillState {
  return {
    expanded: {
      up: isExpanded(state, id, 'up'),
      down: isExpanded(state, id, 'down'),
    },
    loading: {
      up: loading.has(expansionId(id, 'up')),
      down: loading.has(expansionId(id, 'down')),
    },
  }
}

// ---------------------------------------------------------------------------
// Object level
// ---------------------------------------------------------------------------

export type ObjectNodeData = PillState & {
  node: LineageNode
  isFocus: boolean
  more: LineageMore
}

export type ObjectFlowNode = Node<ObjectNodeData, 'object'>

export type LineageEdgeData = {
  kind: EdgeKind
  resolution: Resolution
  detail?: string | null
  highlighted: boolean
  dimmed: boolean
}

export type LineageFlowEdge = Edge<LineageEdgeData, 'lineage'>

const ORIGIN = { x: 0, y: 0 }

function resolvePosition<N extends { id: string }>(
  state: GraphState<N & { more: LineageMore }, LineageEdge | ColumnLineageEdge>,
  id: string,
  positions: Positions,
): { x: number; y: number } {
  const own = positions.get(id)
  if (own) return own
  const seed = state.nodes.get(id)?.seedFrom
  if (seed) {
    const p = positions.get(seed)
    if (p) return p
  }
  return ORIGIN
}

export function toObjectFlowNodes(
  state: GraphState<LineageNode, LineageEdge>,
  positions: Positions,
  opts: { loading: ReadonlySet<string> },
): ObjectFlowNode[] {
  return visibleNodes(state).map((node) => ({
    id: node.id,
    type: 'object',
    position: resolvePosition(state, node.id, positions),
    width: OBJECT_NODE_WIDTH,
    height: OBJECT_NODE_HEIGHT,
    connectable: false,
    draggable: true,
    data: {
      node,
      isFocus: node.id === state.focus,
      more: { ...node.more },
      ...pillState(state, node.id, opts.loading),
    },
  }))
}

export function toObjectFlowEdges(
  state: GraphState<LineageNode, LineageEdge>,
  opts: { hiddenKinds: ReadonlySet<EdgeKind>; hoveredNodeId: string | null },
): LineageFlowEdge[] {
  const hovered = opts.hoveredNodeId
  return visibleEdges(state)
    .filter((e) => !opts.hiddenKinds.has(e.kind))
    .map((e) => {
      const highlighted = hovered != null && (e.source === hovered || e.target === hovered)
      return {
        id: e.id,
        type: 'lineage',
        source: e.source,
        target: e.target,
        data: {
          kind: e.kind,
          resolution: e.resolution,
          detail: e.detail,
          highlighted,
          dimmed: hovered != null && !highlighted,
        },
        zIndex: highlighted ? 1 : 0,
      }
    })
}

// ---------------------------------------------------------------------------
// Column level
// ---------------------------------------------------------------------------

export type ColumnRow = {
  name: string
  data_type?: string | null
  participating: boolean
}

export type ColumnNodeData = PillState & {
  node: ColumnLineageNode
  isFocus: boolean
  focusColumn: string | null
  columns: ColumnRow[]
  hasMoreColumns: boolean
  showAll: boolean
}

export type ColumnFlowNode = Node<ColumnNodeData, 'columnTable'>

export type ColumnEdgeData = {
  confidence: Confidence
  transform: Transform
  via?: string | null
  expression?: string | null
  sourceColumn: string
  targetColumn: string
  highlighted: boolean
}

export type ColumnFlowEdge = Edge<ColumnEdgeData, 'columnLineage'>

export function toColumnFlowNodes(
  state: GraphState<ColumnLineageNode, ColumnLineageEdge>,
  positions: Positions,
  opts: {
    showAll: ReadonlySet<string>
    allColumns: ReadonlyMap<string, readonly string[]>
    focusColumn?: string | null
    /** In-flight expansion ids (`expansionId(nodeId, dir)`), same set as for object nodes. */
    loading: ReadonlySet<string>
  },
): ColumnFlowNode[] {
  return visibleNodes(state).map((node) => {
    const nodeColumns = node.columns ?? []
    const participating = new Set(nodeColumns.map((c) => c.name))
    const typeOf = new Map(nodeColumns.map((c) => [c.name, c.data_type ?? null]))
    const hasMoreColumns = node.column_count_total > nodeColumns.length
    const full = opts.allColumns.get(node.id)
    const showAll = opts.showAll.has(node.id) && !!full
    const columns: ColumnRow[] = showAll
      ? full.map((name) => ({ name, data_type: typeOf.get(name) ?? null, participating: participating.has(name) }))
      : nodeColumns.map((c) => ({ name: c.name, data_type: c.data_type ?? null, participating: true }))
    return {
      id: node.id,
      type: 'columnTable',
      position: resolvePosition(state, node.id, positions),
      width: COLUMN_NODE_WIDTH,
      height: columnNodeHeight(columns.length, hasMoreColumns),
      connectable: false,
      draggable: true,
      data: {
        node,
        isFocus: node.id === state.focus,
        focusColumn: node.id === state.focus ? (opts.focusColumn ?? null) : null,
        columns,
        hasMoreColumns,
        showAll,
        ...pillState(state, node.id, opts.loading),
      },
    }
  })
}

export function toColumnFlowEdges(
  state: GraphState<ColumnLineageNode, ColumnLineageEdge>,
  opts: { minConfidence: Confidence; hoveredNodeId?: string | null },
): ColumnFlowEdge[] {
  const min = CONFIDENCE_RANK[opts.minConfidence]
  const hovered = opts.hoveredNodeId ?? null
  return visibleEdges(state)
    .filter((e) => CONFIDENCE_RANK[e.confidence] >= min)
    .map((e) => ({
      id: e.id,
      type: 'columnLineage',
      source: e.source,
      sourceHandle: handleId('out', e.source_column),
      target: e.target,
      targetHandle: handleId('in', e.target_column),
      data: {
        confidence: e.confidence,
        transform: e.transform,
        via: e.via_name ?? null,
        expression: e.expression ?? null,
        sourceColumn: e.source_column,
        targetColumn: e.target_column,
        highlighted: hovered != null && (e.source === hovered || e.target === hovered),
      },
    }))
}
