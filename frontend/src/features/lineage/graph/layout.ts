import type { ElkExtendedEdge, ElkNode, ElkPort, LayoutOptions } from 'elkjs/lib/elk-api'
import type { Positions } from './to-flow'

export interface LayoutNodeInput {
  id: string
  width: number
  height: number
  ports?: ElkPort[]
}

export interface LayoutEdgeInput {
  id: string
  source: string
  target: string
  sourcePort?: string
  targetPort?: string
}

/** Layout options from the spec: layered, left→right, Brandes-Köpf, model order respected. */
export const ELK_OPTIONS: LayoutOptions = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.layered.spacing.nodeNodeBetweenLayers': '96',
  'elk.spacing.nodeNode': '32',
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
  'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
  'elk.layered.cycleBreaking.strategy': 'GREEDY',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.layered.spacing.edgeNodeBetweenLayers': '24',
  'elk.spacing.edgeNode': '16',
  'elk.spacing.portPort': '8',
}

type Elk = { layout: (graph: ElkNode, args?: { layoutOptions?: LayoutOptions }) => Promise<ElkNode> }
let elkPromise: Promise<Elk> | null = null

async function getElk(): Promise<Elk> {
  elkPromise ??= import('elkjs/lib/elk.bundled.js').then((m) => new m.default() as unknown as Elk)
  return elkPromise
}

/**
 * Runs ELK and returns node positions only (edges are drawn by React Flow).
 * `order` is the stable first-seen order; ELK's model-order strategy keeps siblings from jumping.
 * `hints` are previous positions — they are attached so INTERACTIVE strategies can use them.
 */
export async function layoutGraph(
  nodes: LayoutNodeInput[],
  edges: LayoutEdgeInput[],
  opts: { order?: readonly string[]; hints?: Positions; interactive?: boolean } = {},
): Promise<Map<string, { x: number; y: number }>> {
  if (nodes.length === 0) return new Map()
  const rank = new Map((opts.order ?? []).map((id, i) => [id, i]))
  const sorted = [...nodes].sort((a, b) => (rank.get(a.id) ?? 1e9) - (rank.get(b.id) ?? 1e9))
  const ids = new Set(nodes.map((n) => n.id))

  const children: ElkNode[] = sorted.map((n) => {
    const hint = opts.hints?.get(n.id)
    return {
      id: n.id,
      width: n.width,
      height: n.height,
      ...(hint ? { x: hint.x, y: hint.y } : {}),
      ...(n.ports?.length ? { ports: n.ports, layoutOptions: { 'elk.portConstraints': 'FIXED_POS' } } : {}),
    }
  })
  const elkEdges: ElkExtendedEdge[] = edges
    .filter((e) => ids.has(e.source) && ids.has(e.target) && e.source !== e.target)
    .map((e) => ({ id: e.id, sources: [e.sourcePort ?? e.source], targets: [e.targetPort ?? e.target] }))

  const layoutOptions: LayoutOptions = opts.interactive
    ? { ...ELK_OPTIONS, 'elk.layered.nodePlacement.strategy': 'INTERACTIVE', 'elk.layered.crossingMinimization.strategy': 'INTERACTIVE', 'elk.layered.cycleBreaking.strategy': 'INTERACTIVE' }
    : ELK_OPTIONS

  const elk = await getElk()
  const result = await elk.layout({ id: 'root', layoutOptions, children, edges: elkEdges })
  const out = new Map<string, { x: number; y: number }>()
  for (const c of result.children ?? []) out.set(c.id, { x: Math.round(c.x ?? 0), y: Math.round(c.y ?? 0) })
  return out
}
