import { describe, expect, it } from 'vitest'
import type { ColumnLineageEdge, ColumnLineageNode, LineageEdge, LineageNode } from '@/api/types'
import { createGraphState, graphReducer } from './graph-state'
import {
  COLUMN_HEADER_H,
  COLUMN_NODE_WIDTH,
  COLUMN_ROW_H,
  OBJECT_NODE_HEIGHT,
  OBJECT_NODE_WIDTH,
} from './sizes'
import { toColumnFlowEdges, toColumnFlowNodes, toObjectFlowEdges, toObjectFlowNodes } from './to-flow'

function onode(id: string, hop = 0, more = { upstream: 0, downstream: 0 }): LineageNode {
  return {
    id,
    object_id: 1,
    db: 'AW',
    schema: 'Sales',
    name: id,
    kind: hop === 0 ? 'view' : 'table',
    scope: 'in_scope',
    hop,
    has_lineage_issues: false,
    more,
  }
}

function oedge(source: string, target: string, kind: LineageEdge['kind'] = 'catalog'): LineageEdge {
  return { id: `${source}->${target}`, source, target, kind, resolution: 'resolved' }
}

function objectState() {
  const s0 = graphReducer(createGraphState<LineageNode, LineageEdge>(), {
    type: 'reset',
    focus: 'o:1',
    nodes: [onode('o:1', 0, { upstream: 2, downstream: 0 }), onode('o:2', -1), onode('o:3', 1)],
    edges: [oedge('o:2', 'o:1', 'fk'), oedge('o:1', 'o:3', 'trigger')],
    truncated: false,
    total: 3,
  })
  return graphReducer(s0, {
    type: 'expand',
    nodeId: 'o:1',
    direction: 'up',
    nodes: [onode('o:1', 0, { upstream: 0, downstream: 0 }), onode('o:4', -1)],
    edges: [oedge('o:4', 'o:1')],
  })
}

describe('toObjectFlowNodes', () => {
  it('maps every visible node to a React Flow node with deterministic size and position', () => {
    const s = objectState()
    const positions = new Map([
      ['o:1', { x: 300, y: 0 }],
      ['o:2', { x: 0, y: 0 }],
      ['o:3', { x: 600, y: 0 }],
    ])
    const nodes = toObjectFlowNodes(s, positions, { loading: new Set() })
    expect(nodes.map((n) => n.id)).toEqual(['o:1', 'o:2', 'o:3', 'o:4'])
    expect(nodes.every((n) => n.type === 'object')).toBe(true)
    expect(nodes[0].position).toEqual({ x: 300, y: 0 })
    expect(nodes[0].width).toBe(OBJECT_NODE_WIDTH)
    expect(nodes[0].height).toBe(OBJECT_NODE_HEIGHT)
    expect(nodes[0].data.isFocus).toBe(true)
    expect(nodes[1].data.isFocus).toBe(false)
    // never connectable/draggable-by-default noise
    expect(nodes[0].connectable).toBe(false)
  })

  it('seeds nodes without a layout position at their parent position', () => {
    const s = objectState()
    const positions = new Map([['o:1', { x: 300, y: 40 }]])
    const nodes = toObjectFlowNodes(s, positions, { loading: new Set() })
    const n4 = nodes.find((n) => n.id === 'o:4')!
    expect(n4.position).toEqual({ x: 300, y: 40 })
    const n2 = nodes.find((n) => n.id === 'o:2')!
    expect(n2.position).toEqual({ x: 0, y: 0 })
  })

  it('exposes expand-pill state (remaining counts + expanded/loading flags) in node data', () => {
    const s = objectState()
    const nodes = toObjectFlowNodes(s, new Map(), { loading: new Set(['down:o:3']) })
    const n1 = nodes.find((n) => n.id === 'o:1')!
    expect(n1.data.more).toEqual({ upstream: 0, downstream: 0 })
    expect(n1.data.expanded).toEqual({ up: true, down: false })
    const n3 = nodes.find((n) => n.id === 'o:3')!
    expect(n3.data.loading).toEqual({ up: false, down: true })
  })

  it('omits hidden nodes', () => {
    const s = graphReducer(objectState(), { type: 'hide', nodeId: 'o:3' })
    const ids = toObjectFlowNodes(s, new Map(), { loading: new Set() }).map((n) => n.id)
    expect(ids).not.toContain('o:3')
  })
})

describe('toObjectFlowEdges', () => {
  it('maps visible edges, styled by kind, and drops edges whose kind is toggled off', () => {
    const s = objectState()
    const edges = toObjectFlowEdges(s, { hiddenKinds: new Set(), hoveredNodeId: null })
    expect(edges.map((e) => e.id).sort()).toEqual(['o:1->o:3', 'o:2->o:1', 'o:4->o:1'])
    expect(edges.every((e) => e.type === 'lineage')).toBe(true)
    expect(edges.find((e) => e.id === 'o:2->o:1')!.data!.kind).toBe('fk')
    const filtered = toObjectFlowEdges(s, { hiddenKinds: new Set(['fk']), hoveredNodeId: null })
    expect(filtered.map((e) => e.id)).not.toContain('o:2->o:1')
  })

  it('flags edges adjacent to the hovered node', () => {
    const s = objectState()
    const edges = toObjectFlowEdges(s, { hiddenKinds: new Set(), hoveredNodeId: 'o:3' })
    expect(edges.find((e) => e.id === 'o:1->o:3')!.data!.highlighted).toBe(true)
    expect(edges.find((e) => e.id === 'o:2->o:1')!.data!.highlighted).toBe(false)
  })

  it('drops edges to hidden nodes', () => {
    const s = graphReducer(objectState(), { type: 'hide', nodeId: 'o:3' })
    const edges = toObjectFlowEdges(s, { hiddenKinds: new Set(), hoveredNodeId: null })
    expect(edges.map((e) => e.id)).not.toContain('o:1->o:3')
  })
})

function cnode(id: string, columns: string[], total = columns.length, hop = 0): ColumnLineageNode {
  return {
    id,
    object_id: 1,
    db: 'AW',
    schema: 'Person',
    name: id,
    kind: 'table',
    scope: 'in_scope',
    hop,
    has_lineage_issues: false,
    more: { upstream: 0, downstream: 0 },
    columns: columns.map((name, i) => ({ column_id: i + 1, name, data_type: 'nvarchar(50)' })),
    column_count_total: total,
  }
}

function columnState() {
  return graphReducer(createGraphState<ColumnLineageNode, ColumnLineageEdge>(), {
    type: 'reset',
    focus: 'o:1',
    nodes: [cnode('o:1', ['FirstName', 'LastName'], 5), cnode('o:2', ['FirstName', 'LastName'], 2, -1)],
    edges: [
      {
        id: 'c1',
        source: 'o:2',
        source_column: 'FirstName',
        target: 'o:1',
        target_column: 'FirstName',
        confidence: 'exact',
        transform: 'passthrough',
      },
      {
        id: 'c2',
        source: 'o:2',
        source_column: 'LastName',
        target: 'o:1',
        target_column: 'LastName',
        confidence: 'inferred',
        transform: 'expression',
        via_name: 'Sales.vIndividualCustomer',
        expression: 'UPPER(p.LastName)',
      },
    ],
    truncated: false,
    total: 2,
  })
}

describe('toColumnFlowNodes', () => {
  it('sizes column-table nodes from their row count, with a footer only when columns are hidden', () => {
    const s = columnState()
    const nodes = toColumnFlowNodes(s, new Map(), { showAll: new Set(), allColumns: new Map(), loading: new Set() })
    const n1 = nodes.find((n) => n.id === 'o:1')!
    expect(n1.type).toBe('columnTable')
    expect(n1.width).toBe(COLUMN_NODE_WIDTH)
    expect(n1.height).toBeGreaterThan(COLUMN_HEADER_H + 2 * COLUMN_ROW_H) // has "show all 5" footer
    expect(n1.data.hasMoreColumns).toBe(true)
    const n2 = nodes.find((n) => n.id === 'o:2')!
    expect(n2.height).toBe(COLUMN_HEADER_H + 2 * COLUMN_ROW_H)
    expect(n2.data.hasMoreColumns).toBe(false)
  })

  it('exposes expand-pill state (expanded/loading per direction) exactly like object nodes', () => {
    const s = graphReducer(columnState(), {
      type: 'expand',
      nodeId: 'o:1',
      direction: 'down',
      nodes: [cnode('o:1', ['FirstName', 'LastName'], 5), cnode('o:3', ['FirstName'], 1, 1)],
      edges: [
        {
          id: 'c3',
          source: 'o:1',
          source_column: 'FirstName',
          target: 'o:3',
          target_column: 'FirstName',
          confidence: 'exact',
          transform: 'passthrough',
        },
      ],
    })
    const nodes = toColumnFlowNodes(s, new Map(), { showAll: new Set(), allColumns: new Map(), loading: new Set(['up:o:2']) })
    const n1 = nodes.find((n) => n.id === 'o:1')!
    expect(n1.data.expanded).toEqual({ up: false, down: true })
    expect(n1.data.loading).toEqual({ up: false, down: false })
    const n2 = nodes.find((n) => n.id === 'o:2')!
    expect(n2.data.expanded).toEqual({ up: false, down: false })
    expect(n2.data.loading).toEqual({ up: true, down: false })
    // collapsing clears the flag again so the pill can flip back to `+N`
    const collapsed = toColumnFlowNodes(graphReducer(s, { type: 'collapse', nodeId: 'o:1', direction: 'down' }), new Map(), { showAll: new Set(), allColumns: new Map(), loading: new Set() })
    expect(collapsed.find((n) => n.id === 'o:1')!.data.expanded).toEqual({ up: false, down: false })
    expect(collapsed.map((n) => n.id)).not.toContain('o:3')
  })

  it('shows every column once "show all" is toggled and the full column list is known', () => {
    const s = columnState()
    const all = new Map([['o:1', ['FirstName', 'MiddleName', 'LastName', 'Suffix', 'Title']]])
    const nodes = toColumnFlowNodes(s, new Map(), { showAll: new Set(['o:1']), allColumns: all, loading: new Set() })
    const n1 = nodes.find((n) => n.id === 'o:1')!
    expect(n1.data.columns.map((c) => c.name)).toEqual([
      'FirstName',
      'MiddleName',
      'LastName',
      'Suffix',
      'Title',
    ])
    expect(n1.data.columns.filter((c) => c.participating).map((c) => c.name)).toEqual([
      'FirstName',
      'LastName',
    ])
    expect(n1.height).toBe(COLUMN_HEADER_H + 5 * COLUMN_ROW_H + 22) // footer still present for "show fewer"
  })
})

describe('toColumnFlowEdges', () => {
  it('wires edges to the in:/out: handles and carries confidence + via', () => {
    const s = columnState()
    const edges = toColumnFlowEdges(s, { minConfidence: 'unresolved' })
    expect(edges).toHaveLength(2)
    const e1 = edges.find((e) => e.id === 'c1')!
    expect(e1.type).toBe('columnLineage')
    expect(e1.source).toBe('o:2')
    expect(e1.sourceHandle).toBe('out:FirstName')
    expect(e1.target).toBe('o:1')
    expect(e1.targetHandle).toBe('in:FirstName')
    expect(e1.data!.confidence).toBe('exact')
    const e2 = edges.find((e) => e.id === 'c2')!
    expect(e2.data!.via).toBe('Sales.vIndividualCustomer')
    expect(e2.data!.confidence).toBe('inferred')
  })

  it('filters by minimum confidence', () => {
    const s = columnState()
    expect(toColumnFlowEdges(s, { minConfidence: 'exact' }).map((e) => e.id)).toEqual(['c1'])
    expect(toColumnFlowEdges(s, { minConfidence: 'inferred' })).toHaveLength(2)
  })
})
