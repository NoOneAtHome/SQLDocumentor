import { describe, expect, it } from 'vitest'
import type { LineageEdge, LineageNode } from '@/api/types'
import {
  CLIENT_NODE_CAP,
  ROOT,
  createGraphState,
  expansionId,
  graphReducer,
  isExpanded,
  remainingMore,
  visibleEdges,
  visibleNodes,
} from './graph-state'

function node(id: string, hop = 0, more = { upstream: 0, downstream: 0 }): LineageNode {
  return {
    id,
    object_id: Number(id.replace(/\D/g, '')) || 0,
    db: 'AW',
    schema: 'Sales',
    name: id,
    kind: 'table',
    scope: 'in_scope',
    hop,
    has_lineage_issues: false,
    more,
  }
}

function edge(source: string, target: string): LineageEdge {
  return { id: `${source}->${target}`, source, target, kind: 'catalog', resolution: 'resolved' }
}

function base() {
  return graphReducer(createGraphState<LineageNode, LineageEdge>(), {
    type: 'reset',
    focus: 'o:1',
    nodes: [node('o:1', 0, { upstream: 3, downstream: 1 }), node('o:2', -1), node('o:3', 1)],
    edges: [edge('o:2', 'o:1'), edge('o:1', 'o:3')],
    truncated: false,
    total: 3,
  })
}

describe('graph-state reducer', () => {
  it('reset installs the ego graph with every node added by ROOT', () => {
    const s = base()
    expect(s.focus).toBe('o:1')
    expect(visibleNodes(s).map((n) => n.id)).toEqual(['o:1', 'o:2', 'o:3'])
    expect(visibleEdges(s).map((e) => e.id)).toEqual(['o:2->o:1', 'o:1->o:3'])
    for (const entry of s.nodes.values()) expect(entry.addedBy.has(ROOT)).toBe(true)
    expect(s.total).toBe(3)
    expect(s.truncated).toBe(false)
  })

  it('expand merges a depth-1 fetch, tags new nodes with the expansion id and clears the pill', () => {
    const s0 = base()
    const s1 = graphReducer(s0, {
      type: 'expand',
      nodeId: 'o:1',
      direction: 'up',
      nodes: [node('o:1', 0, { upstream: 0, downstream: 1 }), node('o:4', -1), node('o:2', -1)],
      edges: [edge('o:4', 'o:1'), edge('o:2', 'o:1')],
    })
    const id = expansionId('o:1', 'up')
    expect(isExpanded(s1, 'o:1', 'up')).toBe(true)
    expect(isExpanded(s1, 'o:1', 'down')).toBe(false)
    expect(visibleNodes(s1).map((n) => n.id)).toEqual(['o:1', 'o:2', 'o:3', 'o:4'])
    expect(s1.nodes.get('o:4')!.addedBy).toEqual(new Set([id]))
    expect(s1.nodes.get('o:4')!.seedFrom).toBe('o:1')
    // existing nodes keep ROOT and additionally get the expansion id
    expect(s1.nodes.get('o:2')!.addedBy.has(ROOT)).toBe(true)
    expect(s1.nodes.get('o:2')!.addedBy.has(id)).toBe(true)
    // the expanded node's `more` for that direction now comes from the fetch (0 → pill flips to −)
    expect(remainingMore(s1, 'o:1')).toEqual({ upstream: 0, downstream: 1 })
    expect(visibleEdges(s1).map((e) => e.id)).toContain('o:4->o:1')
    // edges are de-duplicated by id
    expect(visibleEdges(s1).filter((e) => e.id === 'o:2->o:1')).toHaveLength(1)
  })

  it('collapse removes the expansion, drops nodes whose addedBy set empties and restores the pill', () => {
    const s1 = graphReducer(base(), {
      type: 'expand',
      nodeId: 'o:1',
      direction: 'up',
      nodes: [node('o:1', 0, { upstream: 0, downstream: 1 }), node('o:4', -1), node('o:2', -1)],
      edges: [edge('o:4', 'o:1')],
    })
    const s2 = graphReducer(s1, { type: 'collapse', nodeId: 'o:1', direction: 'up' })
    expect(isExpanded(s2, 'o:1', 'up')).toBe(false)
    expect(visibleNodes(s2).map((n) => n.id)).toEqual(['o:1', 'o:2', 'o:3'])
    expect(s2.nodes.has('o:4')).toBe(false)
    expect(s2.edges.has('o:4->o:1')).toBe(false)
    expect(remainingMore(s2, 'o:1')).toEqual({ upstream: 3, downstream: 1 })
    // ROOT nodes survive even though they were also tagged by the expansion
    expect(s2.nodes.get('o:2')!.addedBy).toEqual(new Set([ROOT]))
  })

  it('collapse cascades through nested expansions rooted on dropped nodes', () => {
    const s1 = graphReducer(base(), {
      type: 'expand',
      nodeId: 'o:1',
      direction: 'up',
      nodes: [node('o:1'), node('o:4', -1, { upstream: 1, downstream: 0 })],
      edges: [edge('o:4', 'o:1')],
    })
    const s2 = graphReducer(s1, {
      type: 'expand',
      nodeId: 'o:4',
      direction: 'up',
      nodes: [node('o:4'), node('o:5', -1)],
      edges: [edge('o:5', 'o:4')],
    })
    expect(visibleNodes(s2)).toHaveLength(5)
    const s3 = graphReducer(s2, { type: 'collapse', nodeId: 'o:1', direction: 'up' })
    expect(visibleNodes(s3).map((n) => n.id)).toEqual(['o:1', 'o:2', 'o:3'])
    expect(s3.expansions.size).toBe(0)
    expect(s3.edges.has('o:5->o:4')).toBe(false)
  })

  it('a node reachable from two expansions survives collapsing one of them', () => {
    const s1 = graphReducer(base(), {
      type: 'expand',
      nodeId: 'o:2',
      direction: 'up',
      nodes: [node('o:2'), node('o:9', -2)],
      edges: [edge('o:9', 'o:2')],
    })
    const s2 = graphReducer(s1, {
      type: 'expand',
      nodeId: 'o:3',
      direction: 'up',
      nodes: [node('o:3'), node('o:9', 0)],
      edges: [edge('o:9', 'o:3')],
    })
    const s3 = graphReducer(s2, { type: 'collapse', nodeId: 'o:2', direction: 'up' })
    expect(s3.nodes.has('o:9')).toBe(true)
    expect(s3.edges.has('o:9->o:2')).toBe(true) // both endpoints still present → true edge stays
    expect(s3.edges.has('o:9->o:3')).toBe(true)
    const s4 = graphReducer(s3, { type: 'collapse', nodeId: 'o:3', direction: 'up' })
    expect(s4.nodes.has('o:9')).toBe(false)
  })

  it('hide keeps the node (and edge ids) but removes it from the visible sets', () => {
    const s1 = graphReducer(base(), { type: 'hide', nodeId: 'o:3' })
    expect(s1.nodes.get('o:3')!.hidden).toBe(true)
    expect(visibleNodes(s1).map((n) => n.id)).toEqual(['o:1', 'o:2'])
    expect(visibleEdges(s1).map((e) => e.id)).toEqual(['o:2->o:1'])
    expect(s1.edges.has('o:1->o:3')).toBe(true)
    const s2 = graphReducer(s1, { type: 'unhideAll' })
    expect(visibleNodes(s2)).toHaveLength(3)
    expect(graphReducer(s1, { type: 'unhide', nodeId: 'o:3' }).nodes.get('o:3')!.hidden).toBe(false)
  })

  it('keeps stable first-seen order across merges', () => {
    const s1 = graphReducer(base(), {
      type: 'expand',
      nodeId: 'o:1',
      direction: 'down',
      nodes: [node('o:1'), node('o:7', 1), node('o:6', 1)],
      edges: [edge('o:1', 'o:7'), edge('o:1', 'o:6')],
    })
    expect(s1.order).toEqual(['o:1', 'o:2', 'o:3', 'o:7', 'o:6'])
    const s2 = graphReducer(s1, {
      type: 'expand',
      nodeId: 'o:1',
      direction: 'up',
      nodes: [node('o:1'), node('o:6', -1), node('o:8', -1)],
      edges: [edge('o:8', 'o:1')],
    })
    expect(s2.order).toEqual(['o:1', 'o:2', 'o:3', 'o:7', 'o:6', 'o:8'])
  })

  it('caps the accumulated node count and flags it', () => {
    const many = Array.from({ length: CLIENT_NODE_CAP + 50 }, (_, i) => node(`o:${100 + i}`, -1))
    const s1 = graphReducer(base(), {
      type: 'expand',
      nodeId: 'o:1',
      direction: 'up',
      nodes: [node('o:1'), ...many],
      edges: many.map((n) => edge(n.id, 'o:1')),
    })
    expect(s1.nodes.size).toBe(CLIENT_NODE_CAP)
    expect(s1.capped).toBe(true)
    expect(base().capped).toBe(false)
  })

  it('reset with a new focus replaces the graph entirely', () => {
    const s1 = graphReducer(base(), {
      type: 'expand',
      nodeId: 'o:1',
      direction: 'up',
      nodes: [node('o:1'), node('o:4', -1)],
      edges: [edge('o:4', 'o:1')],
    })
    const s2 = graphReducer(s1, {
      type: 'reset',
      focus: 'o:4',
      nodes: [node('o:4'), node('o:1', 1)],
      edges: [edge('o:4', 'o:1')],
      truncated: true,
      total: 1340,
    })
    expect(s2.focus).toBe('o:4')
    expect(s2.expansions.size).toBe(0)
    expect(visibleNodes(s2).map((n) => n.id)).toEqual(['o:4', 'o:1'])
    expect(s2.truncated).toBe(true)
    expect(s2.total).toBe(1340)
  })
})
