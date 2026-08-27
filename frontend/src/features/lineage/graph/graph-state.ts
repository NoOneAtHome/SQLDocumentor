/**
 * Expand / collapse / hide bookkeeping for the lineage explorer.
 *
 * Every node records which expansions introduced it (`addedBy`). The base ego-graph is
 * tagged with the permanent ROOT id. Collapsing an expansion removes its id from every node
 * it touched; nodes whose set empties are dropped (cascading through expansions that were
 * rooted on them). Hidden nodes stay in the map with `hidden: true` so edge ids stay stable.
 */

export const ROOT = 'root'
export const CLIENT_NODE_CAP = 600

export type Direction = 'up' | 'down'

export interface BaseNode {
  id: string
  more: { upstream: number; downstream: number }
}

export interface BaseEdge {
  id: string
  source: string
  target: string
}

export interface GraphNodeEntry<N extends BaseNode> {
  node: N
  addedBy: Set<string>
  hidden: boolean
  /** Node whose expansion introduced this one — used to seed its initial position. */
  seedFrom?: string
}

export interface Expansion {
  id: string
  nodeId: string
  direction: Direction
  nodeIds: string[]
  prevMore: number
}

export interface GraphState<N extends BaseNode, E extends BaseEdge> {
  focus: string | null
  nodes: Map<string, GraphNodeEntry<N>>
  edges: Map<string, E>
  /** Stable first-seen order (feeds ELK `considerModelOrder`). */
  order: string[]
  expansions: Map<string, Expansion>
  truncated: boolean
  total: number
  capped: boolean
}

export type GraphAction<N extends BaseNode, E extends BaseEdge> =
  | { type: 'reset'; focus: string; nodes: N[]; edges: E[]; truncated: boolean; total: number }
  | { type: 'expand'; nodeId: string; direction: Direction; nodes: N[]; edges: E[] }
  | { type: 'collapse'; nodeId: string; direction: Direction }
  | { type: 'hide'; nodeId: string }
  | { type: 'unhide'; nodeId: string }
  | { type: 'unhideAll' }

export function expansionId(nodeId: string, direction: Direction): string {
  return `${direction}:${nodeId}`
}

export function createGraphState<N extends BaseNode, E extends BaseEdge>(): GraphState<N, E> {
  return {
    focus: null,
    nodes: new Map(),
    edges: new Map(),
    order: [],
    expansions: new Map(),
    truncated: false,
    total: 0,
    capped: false,
  }
}

function cloneState<N extends BaseNode, E extends BaseEdge>(s: GraphState<N, E>): GraphState<N, E> {
  return {
    ...s,
    nodes: new Map(s.nodes),
    edges: new Map(s.edges),
    order: [...s.order],
    expansions: new Map(s.expansions),
  }
}

function moreKey(direction: Direction): 'upstream' | 'downstream' {
  return direction === 'up' ? 'upstream' : 'downstream'
}

/** Drop every edge that lost an endpoint. */
function pruneEdges<N extends BaseNode, E extends BaseEdge>(s: GraphState<N, E>): void {
  for (const [id, edge] of s.edges) {
    if (!s.nodes.has(edge.source) || !s.nodes.has(edge.target)) s.edges.delete(id)
  }
}

function removeExpansion<N extends BaseNode, E extends BaseEdge>(
  s: GraphState<N, E>,
  expId: string,
): void {
  const exp = s.expansions.get(expId)
  if (!exp) return
  s.expansions.delete(expId)

  const anchor = s.nodes.get(exp.nodeId)
  if (anchor) {
    const node = { ...anchor.node, more: { ...anchor.node.more, [moreKey(exp.direction)]: exp.prevMore } }
    s.nodes.set(exp.nodeId, { ...anchor, node })
  }

  const dropped: string[] = []
  for (const id of exp.nodeIds) {
    const entry = s.nodes.get(id)
    if (!entry) continue
    const addedBy = new Set(entry.addedBy)
    addedBy.delete(expId)
    if (addedBy.size === 0) {
      s.nodes.delete(id)
      dropped.push(id)
    } else {
      s.nodes.set(id, { ...entry, addedBy })
    }
  }
  if (dropped.length) {
    const droppedSet = new Set(dropped)
    s.order = s.order.filter((id) => !droppedSet.has(id))
    // Cascade: expansions rooted on a dropped node can no longer be collapsed by the user.
    for (const other of [...s.expansions.values()]) {
      if (droppedSet.has(other.nodeId)) removeExpansion(s, other.id)
    }
  }
  pruneEdges(s)
}

export function graphReducer<N extends BaseNode, E extends BaseEdge>(
  state: GraphState<N, E>,
  action: GraphAction<N, E>,
): GraphState<N, E> {
  switch (action.type) {
    case 'reset': {
      const s = createGraphState<N, E>()
      s.focus = action.focus
      s.truncated = action.truncated
      s.total = action.total
      for (const node of action.nodes) {
        if (s.nodes.has(node.id)) continue
        s.nodes.set(node.id, { node, addedBy: new Set([ROOT]), hidden: false })
        s.order.push(node.id)
      }
      for (const edge of action.edges) {
        if (s.nodes.has(edge.source) && s.nodes.has(edge.target)) s.edges.set(edge.id, edge)
      }
      return s
    }

    case 'expand': {
      const s = cloneState(state)
      const expId = expansionId(action.nodeId, action.direction)
      if (s.expansions.has(expId)) removeExpansion(s, expId)

      const anchorEntry = s.nodes.get(action.nodeId)
      const key = moreKey(action.direction)
      const fetchedAnchor = action.nodes.find((n) => n.id === action.nodeId)
      const prevMore = anchorEntry?.node.more[key] ?? 0
      const touched: string[] = []

      for (const node of action.nodes) {
        if (node.id === action.nodeId) continue
        const existing = s.nodes.get(node.id)
        if (existing) {
          const addedBy = new Set(existing.addedBy)
          addedBy.add(expId)
          s.nodes.set(node.id, { ...existing, addedBy })
          touched.push(node.id)
          continue
        }
        if (s.nodes.size >= CLIENT_NODE_CAP) {
          s.capped = true
          continue
        }
        s.nodes.set(node.id, {
          node,
          addedBy: new Set([expId]),
          hidden: false,
          seedFrom: action.nodeId,
        })
        s.order.push(node.id)
        touched.push(node.id)
      }

      if (anchorEntry) {
        const more = { ...anchorEntry.node.more, [key]: fetchedAnchor?.more[key] ?? 0 }
        s.nodes.set(action.nodeId, { ...anchorEntry, node: { ...anchorEntry.node, more } })
      }

      for (const edge of action.edges) {
        if (s.edges.has(edge.id)) continue
        if (s.nodes.has(edge.source) && s.nodes.has(edge.target)) s.edges.set(edge.id, edge)
      }

      s.expansions.set(expId, {
        id: expId,
        nodeId: action.nodeId,
        direction: action.direction,
        nodeIds: touched,
        prevMore,
      })
      return s
    }

    case 'collapse': {
      const expId = expansionId(action.nodeId, action.direction)
      if (!state.expansions.has(expId)) return state
      const s = cloneState(state)
      removeExpansion(s, expId)
      return s
    }

    case 'hide': {
      const entry = state.nodes.get(action.nodeId)
      if (!entry || entry.hidden) return state
      const s = cloneState(state)
      s.nodes.set(action.nodeId, { ...entry, hidden: true })
      return s
    }

    case 'unhide': {
      const entry = state.nodes.get(action.nodeId)
      if (!entry || !entry.hidden) return state
      const s = cloneState(state)
      s.nodes.set(action.nodeId, { ...entry, hidden: false })
      return s
    }

    case 'unhideAll': {
      if (![...state.nodes.values()].some((n) => n.hidden)) return state
      const s = cloneState(state)
      for (const [id, entry] of s.nodes) if (entry.hidden) s.nodes.set(id, { ...entry, hidden: false })
      return s
    }
  }
}

export function isExpanded<N extends BaseNode, E extends BaseEdge>(
  s: GraphState<N, E>,
  nodeId: string,
  direction: Direction,
): boolean {
  return s.expansions.has(expansionId(nodeId, direction))
}

export function remainingMore<N extends BaseNode, E extends BaseEdge>(
  s: GraphState<N, E>,
  nodeId: string,
): { upstream: number; downstream: number } {
  const entry = s.nodes.get(nodeId)
  return entry ? { ...entry.node.more } : { upstream: 0, downstream: 0 }
}

export function visibleNodes<N extends BaseNode, E extends BaseEdge>(s: GraphState<N, E>): N[] {
  const out: N[] = []
  for (const id of s.order) {
    const entry = s.nodes.get(id)
    if (entry && !entry.hidden) out.push(entry.node)
  }
  return out
}

export function visibleEdges<N extends BaseNode, E extends BaseEdge>(s: GraphState<N, E>): E[] {
  const out: E[] = []
  for (const edge of s.edges.values()) {
    const a = s.nodes.get(edge.source)
    const b = s.nodes.get(edge.target)
    if (a && b && !a.hidden && !b.hidden) out.push(edge)
  }
  return out
}

export function hiddenCount<N extends BaseNode, E extends BaseEdge>(s: GraphState<N, E>): number {
  let n = 0
  for (const entry of s.nodes.values()) if (entry.hidden) n++
  return n
}
