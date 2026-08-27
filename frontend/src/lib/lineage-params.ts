import type { EdgeKind, LineageDirection, ObjectKind } from '@/api/types'
import { EDGE_KIND_SET, OBJECT_KIND_SET } from './constants'

export type LineageLevel = 'object' | 'column'

export interface LineageParams {
  db: string
  schema: string
  kind: string
  name: string
  col: string | null
  level: LineageLevel
  dir: LineageDirection
  depth: number
  types: ObjectKind[]
  schemas: string[]
  cascaded: boolean
  external: boolean
  edges: EdgeKind[]
}

export const DEFAULT_LINEAGE_PARAMS: Omit<LineageParams, 'db' | 'schema' | 'kind' | 'name'> = {
  col: null,
  level: 'object',
  dir: 'both',
  depth: 2,
  types: [],
  schemas: [],
  cascaded: true,
  external: true,
  edges: [],
}

export const MIN_DEPTH = 1
export const MAX_DEPTH = 5

function csv(value: string | null): string[] {
  if (!value) return []
  return value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function bool(value: string | null, fallback: boolean): boolean {
  if (value == null) return fallback
  if (value === '0' || value === 'false') return false
  if (value === '1' || value === 'true') return true
  return fallback
}

export function parseLineageParams(sp: URLSearchParams): LineageParams {
  const d = DEFAULT_LINEAGE_PARAMS
  const level = sp.get('level')
  const dir = sp.get('dir')
  const depthRaw = Number.parseInt(sp.get('depth') ?? '', 10)
  const depth = Number.isFinite(depthRaw)
    ? Math.min(MAX_DEPTH, Math.max(MIN_DEPTH, depthRaw))
    : d.depth
  return {
    db: sp.get('db') ?? '',
    schema: sp.get('schema') ?? '',
    kind: sp.get('kind') ?? '',
    name: sp.get('name') ?? '',
    col: sp.get('col') || null,
    level: level === 'column' ? 'column' : 'object',
    dir: dir === 'up' || dir === 'down' ? dir : 'both',
    depth,
    types: csv(sp.get('types')).filter((t): t is ObjectKind => OBJECT_KIND_SET.has(t)),
    schemas: csv(sp.get('schemas')),
    cascaded: bool(sp.get('cascaded'), d.cascaded),
    external: bool(sp.get('external'), d.external),
    edges: csv(sp.get('edges')).filter((e): e is EdgeKind => EDGE_KIND_SET.has(e)),
  }
}

/** Serialise, omitting defaults so URLs stay short and shareable. */
export function serializeLineageParams(p: Partial<LineageParams>): URLSearchParams {
  const d = DEFAULT_LINEAGE_PARAMS
  const q = new URLSearchParams()
  if (p.db) q.set('db', p.db)
  if (p.schema) q.set('schema', p.schema)
  if (p.kind) q.set('kind', p.kind)
  if (p.name) q.set('name', p.name)
  if (p.col) q.set('col', p.col)
  if (p.level && p.level !== d.level) q.set('level', p.level)
  if (p.dir && p.dir !== d.dir) q.set('dir', p.dir)
  if (p.depth != null && p.depth !== d.depth) q.set('depth', String(p.depth))
  if (p.types && p.types.length) q.set('types', p.types.join(','))
  if (p.schemas && p.schemas.length) q.set('schemas', p.schemas.join(','))
  if (p.cascaded === false) q.set('cascaded', '0')
  if (p.external === false) q.set('external', '0')
  if (p.edges && p.edges.length) q.set('edges', p.edges.join(','))
  return q
}
