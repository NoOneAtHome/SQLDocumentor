import type { LineageParams } from './lineage-params'
import { serializeLineageParams } from './lineage-params'

const e = encodeURIComponent

export type ScanId = number | string
export type StatsPage = 'tables' | 'indexes' | 'procs' | 'missing-indexes'
export type ObjectTab =
  | 'overview'
  | 'columns'
  | 'indexes'
  | 'keys'
  | 'parameters'
  | 'definition'
  | 'stats'
  | 'lineage'
  | 'notes'

/**
 * Object address used in URLs. `db`/`schema` are nullable because external objects may lack
 * them; when either is missing the snapshot-local `id` is the only usable address (see
 * `routes.object`), so pass it whenever the caller has it (`ObjectSummary.id`, `LineageNode.object_id`, …).
 */
export interface ObjectRef {
  id?: number | null
  db?: string | null
  schema?: string | null
  kind: string
  name: string
}

export type LineageRouteParams = ObjectRef & Partial<Omit<LineageParams, keyof ObjectRef>>

const withTab = (base: string, tab?: ObjectTab) => (tab && tab !== 'overview' ? `${base}/${tab}` : base)

/** Id-based object detail path (`/s/:scanId/object/:objectId[/:tab]`). Ids are per-scan, so prefer `routes.object`. */
const objectById = (scanId: ScanId, objectId: number, tab?: ObjectTab) =>
  withTab(`/s/${e(String(scanId))}/object/${e(String(objectId))}`, tab)

/** Path builders. Every dynamic segment is encoded with encodeURIComponent. */
export const routes = {
  home: () => '/',
  settings: () => '/settings',
  connectionScans: (connection: string) => `/connections/${e(connection)}/scans`,
  scan: (scanId: ScanId) => `/s/${e(String(scanId))}`,
  db: (scanId: ScanId, db: string) => `/s/${e(String(scanId))}/db/${e(db)}`,
  schema: (scanId: ScanId, db: string, schema: string) =>
    `/s/${e(String(scanId))}/db/${e(db)}/${e(schema)}`,
  kindList: (scanId: ScanId, db: string, schema: string, kind: string) =>
    `/s/${e(String(scanId))}/db/${e(db)}/${e(schema)}/${e(kind)}`,
  /**
   * Object detail. Name-based whenever the object is fully addressed (stable across scans);
   * otherwise (external objects with no db/schema) the id-based path — a name-based path would
   * contain empty segments that no `:param` route can ever match.
   */
  object: (scanId: ScanId, ref: ObjectRef, tab?: ObjectTab) => {
    if ((!ref.db || !ref.schema) && ref.id != null) return objectById(scanId, ref.id, tab)
    return withTab(`/s/${e(String(scanId))}/db/${e(ref.db ?? '')}/${e(ref.schema ?? '')}/${e(ref.kind)}/${e(ref.name)}`, tab)
  },
  objectById,
  lineage: (scanId: ScanId, params: LineageRouteParams) => {
    const q = serializeLineageParams({ ...params, db: params.db ?? '', schema: params.schema ?? '' }).toString()
    return `/s/${e(String(scanId))}/lineage${q ? `?${q}` : ''}`
  },
  stats: (scanId: ScanId, page: StatsPage) => `/s/${e(String(scanId))}/stats/${page}`,
} as const

/** Route patterns used by the router (kept next to the builders so they can't drift apart). */
export const routePatterns = {
  connectionScans: '/connections/:connId/scans',
  scan: '/s/:scanId',
  db: 'db/:db',
  schema: 'db/:db/:schema',
  kindList: 'db/:db/:schema/:kind',
  object: 'db/:db/:schema/:kind/:name',
  objectTab: 'db/:db/:schema/:kind/:name/:tab',
  objectById: 'object/:objectId/:tab?',
  lineage: 'lineage',
  stats: 'stats/:page',
} as const
