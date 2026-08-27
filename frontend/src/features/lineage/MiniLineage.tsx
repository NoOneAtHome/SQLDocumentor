import { Background, BackgroundVariant, ReactFlow, ReactFlowProvider, useReactFlow } from '@xyflow/react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { $api, scanPath } from '@/api/client'
import type { LineageEdge, LineageNode } from '@/api/types'
import { Skeleton } from '@/components/ui/skeleton'
import { SNAPSHOT_QUERY } from '@/lib/constants'
import { type ObjectRef, routes } from '@/lib/routes'
import { useTheme } from '@/lib/theme'
import { LineageActionsContext, type LineageActions } from './actions-context'
import { edgeTypes, nodeTypes } from './flow-types'
import { createGraphState, graphReducer } from './graph/graph-state'
import { layoutGraph } from './graph/layout'
import { OBJECT_NODE_HEIGHT, OBJECT_NODE_WIDTH } from './graph/sizes'
import { type Positions, toObjectFlowEdges, toObjectFlowNodes } from './graph/to-flow'

const NO_HIDDEN = new Set<never>()
const NO_LOADING = new Set<string>()

function Fit({ positions }: { positions: Positions }) {
  const rf = useReactFlow()
  useEffect(() => {
    if (positions.size === 0) return
    const id = requestAnimationFrame(() => void rf.fitView({ padding: 0.15, maxZoom: 1 }))
    return () => cancelAnimationFrame(id)
  }, [positions, rf])
  return null
}

/** Static one-hop lineage preview for Overview tabs; pills navigate to the full explorer. */
export function MiniLineage({ scanId, objectId, focusRef }: { scanId: number; objectId: number; focusRef: ObjectRef }) {
  const { resolved } = useTheme()
  const navigate = useNavigate()
  const q = $api.useQuery(
    'get',
    '/api/scans/{scan_id}/lineage/objects',
    { params: { path: scanPath(scanId), query: { focus: objectId, direction: 'both', depth: 1, max_nodes: 40 } } },
    SNAPSHOT_QUERY,
  )
  const state = useMemo(() => {
    if (!q.data) return null
    return graphReducer(createGraphState<LineageNode, LineageEdge>(), { type: 'reset', focus: q.data.focus, nodes: q.data.nodes, edges: q.data.edges, truncated: q.data.truncated, total: q.data.total })
  }, [q.data])

  const [positions, setPositions] = useState<Positions>(() => new Map())
  useEffect(() => {
    if (!state) return
    let cancelled = false
    const nodes = [...state.nodes.values()].map((e) => ({ id: e.node.id, width: OBJECT_NODE_WIDTH, height: OBJECT_NODE_HEIGHT }))
    const edges = [...state.edges.values()].map((e) => ({ id: e.id, source: e.source, target: e.target }))
    void layoutGraph(nodes, edges, { order: state.order }).then((p) => {
      if (!cancelled) setPositions(p)
    })
    return () => {
      cancelled = true
    }
  }, [state])

  const actions = useMemo<LineageActions>(() => {
    const go = () => navigate(routes.lineage(scanId, focusRef))
    return { expand: go, collapse: go, toggleShowAll: go, selectColumn: go }
  }, [navigate, scanId, focusRef])

  const nodes = useMemo(() => (state ? toObjectFlowNodes(state, positions, { loading: NO_LOADING }).map((n) => ({ ...n, draggable: false })) : []), [state, positions])
  const edges = useMemo(() => (state ? toObjectFlowEdges(state, { hiddenKinds: NO_HIDDEN, hoveredNodeId: null }) : []), [state])

  if (q.isPending || !state || (positions.size === 0 && nodes.length > 0)) return <Skeleton className="h-60 w-full rounded-lg" />
  if (nodes.length <= 1) return <div className="flex h-24 items-center justify-center rounded-lg border border-dashed border-border text-[12.5px] text-muted-foreground">No lineage edges recorded for this object.</div>

  return (
    <LineageActionsContext.Provider value={actions}>
      <div className="h-60 overflow-hidden rounded-lg border border-border">
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            colorMode={resolved}
            fitView
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            zoomOnScroll={false}
            zoomOnDoubleClick={false}
            panOnScroll={false}
            panOnDrag
            preventScrolling={false}
            minZoom={0.2}
            maxZoom={1}
            onNodeDoubleClick={(_, n) => {
              const d = (n.data as { node: LineageNode }).node
              navigate(routes.object(scanId, { id: d.object_id, db: d.db, schema: d.schema, kind: d.kind, name: d.name }))
            }}
          >
            <Fit positions={positions} />
            <Background variant={BackgroundVariant.Dots} gap={22} size={1} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </LineageActionsContext.Provider>
  )
}
