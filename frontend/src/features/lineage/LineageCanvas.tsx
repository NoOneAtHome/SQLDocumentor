import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  type Node,
  type NodeMouseHandler,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
} from '@xyflow/react'
import { Copy, Crosshair, ExternalLink, EyeOff, ListFilter, Minus, MoveLeft, MoveRight } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ColumnLineageEdge, ColumnLineageNode, Confidence, EdgeKind, LineageEdge, LineageNode, ObjectKind } from '@/api/types'
import { Button } from '@/components/ui/button'
import { KIND_COLOR } from '@/lib/constants'
import { formatNumber } from '@/lib/format'
import { useTheme } from '@/lib/theme'
import { cn, copyToClipboard } from '@/lib/utils'
import { fitRef } from './fit-view'
import { edgeTypes, nodeTypes } from './flow-types'
import { type GraphState, isExpanded } from './graph/graph-state'
import { type ColumnFlowNode, type ObjectFlowNode, toColumnFlowEdges, toColumnFlowNodes, toObjectFlowEdges, toObjectFlowNodes } from './graph/to-flow'
import type { LineageEngine } from './hooks/useLineageGraph'
import { LineageLegend } from './LineageLegend'

type FlowNode = ObjectFlowNode | ColumnFlowNode

interface CanvasProps {
  engine: LineageEngine
  selectedId: string | null
  onSelect: (id: string | null) => void
  onRefocus: (nodeId: string) => void
  onOpenDetail: (nodeId: string) => void
  onDepthDown: () => void
  onOpenFilters: () => void
  canDepthDown: boolean
  hiddenKinds: ReadonlySet<EdgeKind>
  onToggleKind: (kind: EdgeKind) => void
  minConfidence: Confidence
  showLegend: boolean
  showMinimap: boolean
  focusColumn: string | null
  embedded?: boolean
}

/** Resolve the `--obj-*` CSS variables once per theme so the minimap (SVG attrs) gets real colours. */
function useKindColors(): Record<string, string> {
  const { resolved } = useTheme()
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement)
    const out: Record<string, string> = {}
    for (const c of ['table', 'view', 'proc', 'function', 'trigger', 'external', 'misc']) out[c] = css.getPropertyValue(`--obj-${c}`).trim() || '#888'
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolved])
}

function CanvasEffects({ change }: { change: LineageEngine['change'] }) {
  const rf = useReactFlow()
  useEffect(() => {
    if (change.type === 'none') return
    const id = requestAnimationFrame(() => {
      if (change.type === 'expand') void rf.fitView({ duration: 300, padding: 0.15, maxZoom: rf.getZoom() })
      else void rf.fitView({ duration: 300, padding: 0.2, maxZoom: 1.1 })
    })
    return () => cancelAnimationFrame(id)
  }, [change, rf])
  return null
}

interface MenuState {
  x: number
  y: number
  nodeId: string
}

function CanvasInner(props: CanvasProps) {
  const { engine, selectedId, onSelect, onRefocus, onOpenDetail, hiddenKinds, minConfidence, focusColumn } = props
  const { resolved } = useTheme()
  const rf = useReactFlow()
  const kindColors = useKindColors()
  const [hovered, setHovered] = useState<string | null>(null)
  const [menu, setMenu] = useState<MenuState | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const computedNodes = useMemo<FlowNode[]>(() => {
    const base: FlowNode[] =
      engine.level === 'object'
        ? toObjectFlowNodes(engine.objectState, engine.positions, { loading: engine.loadingExpansions })
        : toColumnFlowNodes(engine.columnState, engine.positions, { showAll: engine.showAll, allColumns: engine.allColumns, focusColumn, loading: engine.loadingExpansions })
    return base.map((n) => ({ ...n, className: cn(engine.animating && 'is-animating'), selected: n.id === selectedId }))
  }, [engine.level, engine.objectState, engine.columnState, engine.positions, engine.loadingExpansions, engine.showAll, engine.allColumns, engine.animating, selectedId, focusColumn])

  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(computedNodes)
  useEffect(() => setNodes(computedNodes), [computedNodes, setNodes])

  const edges = useMemo(() => {
    if (engine.level === 'object') {
      return toObjectFlowEdges(engine.objectState, { hiddenKinds, hoveredNodeId: hovered ?? selectedId }).map((e) => ({
        ...e,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: 'var(--edge-catalog)' },
      }))
    }
    return toColumnFlowEdges(engine.columnState, { minConfidence, hoveredNodeId: hovered ?? selectedId }).map((e) => ({
      ...e,
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: 'var(--edge-catalog)' },
    }))
  }, [engine.level, engine.objectState, engine.columnState, hiddenKinds, minConfidence, hovered, selectedId])

  const onNodeClick = useCallback<NodeMouseHandler<FlowNode>>((_, node) => onSelect(node.id), [onSelect])
  const onNodeDoubleClick = useCallback<NodeMouseHandler<FlowNode>>((_, node) => onOpenDetail(node.id), [onOpenDetail])
  const onNodeContextMenu = useCallback<NodeMouseHandler<FlowNode>>(
    (e, node) => {
      e.preventDefault()
      const rect = containerRef.current?.getBoundingClientRect()
      setMenu({ x: e.clientX - (rect?.left ?? 0), y: e.clientY - (rect?.top ?? 0), nodeId: node.id })
      onSelect(node.id)
    },
    [onSelect],
  )

  useEffect(() => {
    if (!menu) return
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent && e.key !== 'Escape') return
      setMenu(null)
    }
    window.addEventListener('pointerdown', close, true)
    window.addEventListener('keydown', close)
    return () => {
      window.removeEventListener('pointerdown', close, true)
      window.removeEventListener('keydown', close)
    }
  }, [menu])

  const menuNode = menu ? nodes.find((n) => n.id === menu.nodeId) : null
  const menuState: GraphState<LineageNode | ColumnLineageNode, LineageEdge | ColumnLineageEdge> = engine.level === 'object' ? engine.objectState : engine.columnState
  const nodeColor = useCallback((n: Node) => kindColors[KIND_COLOR[(n.data as { node?: { kind: ObjectKind } }).node?.kind ?? 'table']] ?? '#888', [kindColors])

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <ReactFlow<FlowNode>
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        colorMode={resolved}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.1 }}
        minZoom={0.15}
        maxZoom={2}
        onlyRenderVisibleElements
        nodesConnectable={false}
        elementsSelectable
        selectNodesOnDrag={false}
        zoomOnDoubleClick={false}
        deleteKeyCode={null}
        panOnScroll
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onNodeContextMenu={onNodeContextMenu}
        onNodeMouseEnter={(_, n) => setHovered(n.id)}
        onNodeMouseLeave={() => setHovered(null)}
        onPaneClick={() => {
          onSelect(null)
          setMenu(null)
        }}
        className={cn(engine.layoutPending && 'cursor-progress')}
      >
        <CanvasEffects change={engine.change} />
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} />
        <Controls showInteractive={false} position="bottom-right" />
        {props.showMinimap && <MiniMap pannable zoomable nodeColor={nodeColor} nodeStrokeWidth={0} position="bottom-left" className="!h-24 !w-40" />}

        {(engine.truncated || engine.capped) && (
          <Panel position="top-center">
            <div className="flex items-center gap-2 rounded-md border border-warning/40 bg-card/95 px-3 py-1.5 text-[12px] shadow-sm backdrop-blur">
              <span>
                {engine.capped ? (
                  <>Reached the client cap of {formatNumber(engine.visibleCount)} objects — collapse some expansions to add more.</>
                ) : (
                  <>
                    Showing <b className="font-mono tnum">{formatNumber(engine.visibleCount)}</b> of <b className="font-mono tnum">{formatNumber(engine.total)}</b> objects
                  </>
                )}
              </span>
              {props.canDepthDown && (
                <Button size="xs" variant="outline" onClick={props.onDepthDown}>
                  <Minus /> Depth −1
                </Button>
              )}
              <Button size="xs" variant="outline" onClick={props.onOpenFilters}>
                <ListFilter /> Filter types
              </Button>
            </div>
          </Panel>
        )}

        {engine.hiddenCount > 0 && (
          <Panel position="bottom-center">
            <button type="button" onClick={engine.unhideAll} className="rounded-md border border-border bg-card/95 px-2 py-1 text-[11.5px] text-muted-foreground shadow-sm backdrop-blur hover:text-foreground">
              {engine.hiddenCount} hidden · show all
            </button>
          </Panel>
        )}

        {props.showLegend && (
          <Panel position="top-left">
            <LineageLegend level={engine.level} hiddenKinds={hiddenKinds} onToggleKind={props.onToggleKind} />
          </Panel>
        )}
      </ReactFlow>

      {menu && menuNode && (
        <div
          role="menu"
          style={{ left: menu.x, top: menu.y }}
          className="absolute z-30 w-52 rounded-md border border-border bg-popover p-1 text-[12.5px] text-popover-foreground shadow-md"
          onPointerDown={(e) => e.stopPropagation()}
        >
          <div className="truncate px-2 py-1 font-mono text-[11px] text-muted-foreground">
            {(menuNode.data as { node: { schema?: string | null; name: string } }).node.schema ?? ''}.{(menuNode.data as { node: { schema?: string | null; name: string } }).node.name}
          </div>
          {(
            [
              { icon: Crosshair, label: 'Focus here', shortcut: 'F', run: () => onRefocus(menu.nodeId) },
              {
                icon: MoveLeft,
                label: isExpanded(menuState, menu.nodeId, 'up') ? 'Collapse upstream' : 'Expand upstream',
                run: () => (isExpanded(menuState, menu.nodeId, 'up') ? engine.collapse(menu.nodeId, 'up') : void engine.expand(menu.nodeId, 'up')),
              },
              {
                icon: MoveRight,
                label: isExpanded(menuState, menu.nodeId, 'down') ? 'Collapse downstream' : 'Expand downstream',
                run: () => (isExpanded(menuState, menu.nodeId, 'down') ? engine.collapse(menu.nodeId, 'down') : void engine.expand(menu.nodeId, 'down')),
              },
              { icon: EyeOff, label: 'Hide', shortcut: 'H', run: () => engine.hide(menu.nodeId) },
              { icon: ExternalLink, label: 'Open detail', run: () => onOpenDetail(menu.nodeId) },
              {
                icon: Copy,
                label: 'Copy qualified name',
                run: () => {
                  const d = menuNode.data as { node: { schema?: string | null; name: string } }
                  void copyToClipboard(d.node.schema ? `[${d.node.schema}].[${d.node.name}]` : `[${d.node.name}]`)
                },
              },
            ] as Array<{ icon: typeof Crosshair; label: string; shortcut?: string; run: () => void }>
          ).map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left hover:bg-muted"
              onClick={() => {
                item.run()
                setMenu(null)
              }}
            >
              <item.icon className="size-3.5 text-muted-foreground" />
              <span className="flex-1">{item.label}</span>
              {item.shortcut && <kbd className="font-mono text-[10px] text-muted-foreground">{item.shortcut}</kbd>}
            </button>
          ))}
        </div>
      )}

      <FitBridge rf={rf} />
    </div>
  )
}

function FitBridge({ rf }: { rf: ReturnType<typeof useReactFlow> }) {
  useEffect(() => {
    fitRef.current = () => void rf.fitView({ duration: 250, padding: 0.2 })
    return () => {
      fitRef.current = null
    }
  }, [rf])
  return null
}

export function LineageCanvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  )
}
