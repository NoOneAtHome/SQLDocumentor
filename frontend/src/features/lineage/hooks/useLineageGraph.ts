import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { toast } from 'sonner'
import { $api, scanPath } from '@/api/client'
import type { ColumnLineageEdge, ColumnLineageNode, LineageEdge, LineageNode, ObjectDetail } from '@/api/types'
import { useObjectDetail } from '@/features/objects/hooks/useObjectDetail'
import { COLUMN_LINEAGE_MAX_NODES, LINEAGE_MAX_NODES, SNAPSHOT_QUERY } from '@/lib/constants'
import type { LineageParams } from '@/lib/lineage-params'
import { errorMessage } from '@/lib/utils'
import { type Direction, type GraphState, createGraphState, expansionId, graphReducer, hiddenCount, visibleEdges, visibleNodes } from '../graph/graph-state'
import { type LayoutEdgeInput, type LayoutNodeInput, layoutGraph } from '../graph/layout'
import { COLUMN_NODE_WIDTH, OBJECT_NODE_HEIGHT, OBJECT_NODE_WIDTH, columnNodeHeight, elkPort, portId } from '../graph/sizes'
import type { Positions } from '../graph/to-flow'

export type ChangeKind = 'none' | 'reset' | 'expand' | 'relayout'

export interface LineageEngine {
  level: 'object' | 'column'
  status: 'empty' | 'resolving' | 'loading' | 'ready' | 'error'
  error: unknown
  focusDetail: ObjectDetail | undefined
  focusNodeId: string | null
  objectState: GraphState<LineageNode, LineageEdge>
  columnState: GraphState<ColumnLineageNode, ColumnLineageEdge>
  positions: Positions
  layoutPending: boolean
  animating: boolean
  loadingExpansions: ReadonlySet<string>
  showAll: ReadonlySet<string>
  allColumns: ReadonlyMap<string, readonly string[]>
  change: { type: ChangeKind; version: number }
  truncated: boolean
  total: number
  capped: boolean
  hiddenCount: number
  visibleCount: number
  expand: (nodeId: string, direction: Direction) => Promise<void>
  collapse: (nodeId: string, direction: Direction) => void
  hide: (nodeId: string) => void
  unhideAll: () => void
  relayout: () => void
  toggleShowAll: (nodeId: string) => Promise<void>
  retry: () => void
}

const objectReducer = graphReducer<LineageNode, LineageEdge>
const columnReducer = graphReducer<ColumnLineageNode, ColumnLineageEdge>

function parseObjectId(nodeId: string): number {
  const m = /^o:(\d+)$/.exec(nodeId)
  return m ? Number(m[1]) : Number(nodeId)
}

/**
 * Drives the explorer: resolves the focus by name, loads the ego graph, keeps expand/collapse/hide
 * bookkeeping in the reducer, and runs ELK whenever the visible node set (or node sizes) change.
 */
export function useLineageEngine(scanId: number, params: LineageParams): LineageEngine {
  const qc = useQueryClient()
  const level = params.level
  const hasFocus = !!params.name && !!params.schema
  const lookup = useObjectDetail(scanId, { db: params.db, schema: params.schema, name: params.name }, { enabled: hasFocus })
  const focusId = lookup.data?.summary.id ?? null

  const filterQuery = useMemo(
    () => ({
      kinds: params.types.length ? params.types.join(',') : undefined,
      schemas: params.schemas.length ? params.schemas.join(',') : undefined,
      edge_kinds: params.edges.length ? params.edges.join(',') : undefined,
      include_cascaded: params.cascaded,
      include_external: params.external,
    }),
    [params.types, params.schemas, params.edges, params.cascaded, params.external],
  )

  const objectQuery = $api.useQuery(
    'get',
    '/api/scans/{scan_id}/lineage/objects',
    { params: { path: scanPath(scanId), query: { focus: focusId ?? 0, direction: params.dir, depth: params.depth, ...filterQuery, max_nodes: LINEAGE_MAX_NODES } } },
    { ...SNAPSHOT_QUERY, enabled: focusId != null && level === 'object' },
  )
  const columnQuery = $api.useQuery(
    'get',
    '/api/scans/{scan_id}/lineage/columns',
    { params: { path: scanPath(scanId), query: { focus: focusId ?? 0, column: params.col ?? undefined, direction: params.dir, depth: params.depth, min_confidence: 'unresolved', max_nodes: COLUMN_LINEAGE_MAX_NODES } } },
    { ...SNAPSHOT_QUERY, enabled: focusId != null && level === 'column' },
  )

  const [objectState, dispatchObject] = useReducer(objectReducer, undefined, createGraphState<LineageNode, LineageEdge>)
  const [columnState, dispatchColumn] = useReducer(columnReducer, undefined, createGraphState<ColumnLineageNode, ColumnLineageEdge>)
  const [positions, setPositions] = useState<Positions>(() => new Map())
  const [layoutPending, setLayoutPending] = useState(false)
  const [animating, setAnimating] = useState(false)
  const [loadingExpansions, setLoadingExpansions] = useState<ReadonlySet<string>>(() => new Set())
  const [showAll, setShowAll] = useState<ReadonlySet<string>>(() => new Set())
  const [allColumns, setAllColumns] = useState<ReadonlyMap<string, readonly string[]>>(() => new Map())
  const [change, setChange] = useState<{ type: ChangeKind; version: number }>({ type: 'none', version: 0 })
  // The change kind is recorded when data arrives and published only once ELK has produced
  // positions, so `fitView` sees the final geometry.
  const pendingChangeRef = useRef<ChangeKind>('none')
  const bump = useCallback((type: ChangeKind) => {
    pendingChangeRef.current = type
  }, [])

  // Base graph → reducer reset.
  const objectData = objectQuery.data
  useEffect(() => {
    if (level !== 'object' || !objectData) return
    dispatchObject({ type: 'reset', focus: objectData.focus, nodes: objectData.nodes, edges: objectData.edges, truncated: objectData.truncated, total: objectData.total })
    bump('reset')
  }, [objectData, level, bump])
  const columnData = columnQuery.data
  useEffect(() => {
    if (level !== 'column' || !columnData) return
    dispatchColumn({ type: 'reset', focus: `o:${columnData.focus.object_id}`, nodes: columnData.nodes, edges: columnData.edges, truncated: columnData.truncated, total: columnData.total })
    setShowAll(new Set())
    bump('reset')
  }, [columnData, level, bump])

  // Layout whenever the visible set or sizes change.
  const layoutInput = useMemo(() => {
    if (level === 'object') {
      const nodes: LayoutNodeInput[] = visibleNodes(objectState).map((n) => ({ id: n.id, width: OBJECT_NODE_WIDTH, height: OBJECT_NODE_HEIGHT }))
      const edges: LayoutEdgeInput[] = visibleEdges(objectState).map((e) => ({ id: e.id, source: e.source, target: e.target }))
      return { nodes, edges, order: objectState.order }
    }
    const nodes: LayoutNodeInput[] = visibleNodes(columnState).map((n) => {
      const full = showAll.has(n.id) ? allColumns.get(n.id) : undefined
      const participating = n.columns ?? []
      const names = full ?? participating.map((c) => c.name)
      const hasFooter = n.column_count_total > participating.length
      const ports = names.flatMap((name, i) => [elkPort(n.id, 'in', name, i), elkPort(n.id, 'out', name, i)])
      return { id: n.id, width: COLUMN_NODE_WIDTH, height: columnNodeHeight(names.length, hasFooter), ports }
    })
    const edges: LayoutEdgeInput[] = visibleEdges(columnState).map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourcePort: portId(e.source, 'out', e.source_column),
      targetPort: portId(e.target, 'in', e.target_column),
    }))
    return { nodes, edges, order: columnState.order }
  }, [level, objectState, columnState, showAll, allColumns])

  const signature = useMemo(
    () => `${level}|${layoutInput.nodes.map((n) => `${n.id}:${n.width}x${n.height}:${n.ports?.length ?? 0}`).join(',')}|${layoutInput.edges.map((e) => e.id).join(',')}`,
    [level, layoutInput],
  )
  const [relayoutTick, setRelayoutTick] = useState(0)
  const runRef = useRef(0)
  const positionsRef = useRef(positions)
  positionsRef.current = positions

  useEffect(() => {
    if (layoutInput.nodes.length === 0) {
      setPositions(new Map())
      return
    }
    const run = ++runRef.current
    setLayoutPending(true)
    layoutGraph(layoutInput.nodes, layoutInput.edges, { order: layoutInput.order, hints: positionsRef.current })
      .then((next) => {
        if (run !== runRef.current) return
        setPositions(next)
        setLayoutPending(false)
        setAnimating(true)
        setTimeout(() => setAnimating(false), 320)
        const kind = pendingChangeRef.current === 'none' ? 'relayout' : pendingChangeRef.current
        pendingChangeRef.current = 'none'
        setChange((c) => ({ type: kind, version: c.version + 1 }))
      })
      .catch((e) => {
        if (run !== runRef.current) return
        setLayoutPending(false)
        toast.error('Layout failed', { description: errorMessage(e) })
      })
    // signature captures everything layout depends on; layoutInput identity changes more often.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, relayoutTick])

  const expand = useCallback(
    async (nodeId: string, direction: Direction) => {
      const expId = expansionId(nodeId, direction)
      setLoadingExpansions((s) => new Set(s).add(expId))
      try {
        const objectId = parseObjectId(nodeId)
        if (level === 'object') {
          const data = await qc.fetchQuery(
            $api.queryOptions(
              'get',
              '/api/scans/{scan_id}/lineage/objects',
              { params: { path: scanPath(scanId), query: { focus: objectId, direction, depth: 1, ...filterQuery, max_nodes: 100 } } },
              SNAPSHOT_QUERY,
            ),
          )
          dispatchObject({ type: 'expand', nodeId, direction, nodes: data.nodes, edges: data.edges })
        } else {
          const data = await qc.fetchQuery(
            $api.queryOptions(
              'get',
              '/api/scans/{scan_id}/lineage/columns',
              { params: { path: scanPath(scanId), query: { focus: objectId, direction, depth: 1, min_confidence: 'unresolved', max_nodes: 60 } } },
              SNAPSHOT_QUERY,
            ),
          )
          dispatchColumn({ type: 'expand', nodeId, direction, nodes: data.nodes, edges: data.edges })
        }
        bump('expand')
      } catch (e) {
        toast.error('Could not expand', { description: errorMessage(e) })
      } finally {
        setLoadingExpansions((s) => {
          const n = new Set(s)
          n.delete(expId)
          return n
        })
      }
    },
    [level, qc, scanId, filterQuery, bump],
  )

  const collapse = useCallback(
    (nodeId: string, direction: Direction) => {
      if (level === 'object') dispatchObject({ type: 'collapse', nodeId, direction })
      else dispatchColumn({ type: 'collapse', nodeId, direction })
      bump('expand')
    },
    [level, bump],
  )

  const hide = useCallback(
    (nodeId: string) => {
      if (level === 'object') dispatchObject({ type: 'hide', nodeId })
      else dispatchColumn({ type: 'hide', nodeId })
    },
    [level],
  )

  const unhideAll = useCallback(() => {
    if (level === 'object') dispatchObject({ type: 'unhideAll' })
    else dispatchColumn({ type: 'unhideAll' })
  }, [level])

  const relayout = useCallback(() => {
    setRelayoutTick((t) => t + 1)
    bump('relayout')
  }, [bump])

  const toggleShowAll = useCallback(
    async (nodeId: string) => {
      if (!allColumns.has(nodeId)) {
        try {
          const detail = await qc.fetchQuery(
            $api.queryOptions('get', '/api/scans/{scan_id}/objects/{object_id}', { params: { path: { scan_id: scanId, object_id: parseObjectId(nodeId) } } }, SNAPSHOT_QUERY),
          )
          setAllColumns((m) => new Map(m).set(nodeId, (detail.columns ?? []).map((c) => c.name)))
        } catch (e) {
          toast.error('Could not load columns', { description: errorMessage(e) })
          return
        }
      }
      setShowAll((s) => {
        const n = new Set(s)
        if (n.has(nodeId)) n.delete(nodeId)
        else n.add(nodeId)
        return n
      })
    },
    [allColumns, qc, scanId],
  )

  const activeQuery = level === 'object' ? objectQuery : columnQuery
  const activeState: GraphState<LineageNode | ColumnLineageNode, LineageEdge | ColumnLineageEdge> = level === 'object' ? objectState : columnState
  const status: LineageEngine['status'] = !hasFocus
    ? 'empty'
    : lookup.isPending
      ? 'resolving'
      : lookup.error || activeQuery.error
        ? 'error'
        : activeQuery.isPending || activeState.focus == null
          ? 'loading'
          : 'ready'

  const retry = useCallback(() => {
    if (lookup.error) void lookup.refetch()
    else void activeQuery.refetch()
  }, [lookup, activeQuery])

  return {
    level,
    status,
    error: lookup.error ?? activeQuery.error,
    focusDetail: lookup.data,
    focusNodeId: focusId != null ? `o:${focusId}` : null,
    objectState,
    columnState,
    positions,
    layoutPending,
    animating,
    loadingExpansions,
    showAll,
    allColumns,
    change,
    truncated: activeState.truncated,
    total: activeState.total,
    capped: activeState.capped,
    hiddenCount: hiddenCount(activeState),
    visibleCount: visibleNodes(activeState).length,
    expand,
    collapse,
    hide,
    unhideAll,
    relayout,
    toggleShowAll,
    retry,
  }
}
