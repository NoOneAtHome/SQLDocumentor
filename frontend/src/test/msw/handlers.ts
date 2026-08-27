/**
 * MSW handlers implementing the canonical API contract against the fixture snapshot.
 * Used by `npm run dev:mock` (browser worker) and by vitest (node server).
 */
import { HttpResponse, delay, http } from 'msw'
import type {
  Annotation,
  AnnotationUpsert,
  Column,
  ColumnLineageEdge,
  ColumnLineageGraph,
  ColumnLineageNode,
  Confidence,
  DepRef,
  EdgeKind,
  ExecStats,
  ForeignKey,
  IndexStatsRow,
  LineageHub,
  ObjectRefLite,
  LineageEdge,
  LineageGraph,
  LineageNode,
  MissingIndexRow,
  ObjectDetail,
  ObjectKind,
  ObjectSummary,
  Paged,
  ProcStatsRow,
  ScanDetail,
  ScanPhase,
  ScanProgress,
  ScanSummary,
  SearchColumnHit,
  SearchObjectHit,
  SearchResult,
  SnapshotSummary,
  TableStats,
  TableStatsRow,
  Tag,
} from '@/api/types'
import { CONFIDENCE_RANK, SCAN_PHASES } from '@/lib/constants'
import {
  COLUMN_EDGES,
  CONNECTION,
  DB,
  type FixtureColumn,
  EDGES,
  EMPTY_COUNTS,
  type FixtureObject,
  INITIAL_ANNOTATIONS,
  INITIAL_SCANS,
  OBJECTS,
  SCAN_COUNTS,
  SCAN_OPTIONS,
  SELECTED_SCHEMAS,
  TAG_COLORS,
} from './fixtures'

// ---------------------------------------------------------------------------
// Mutable state (scans + annotations); everything else is immutable snapshot data.
// ---------------------------------------------------------------------------

const PHASE_MS = 850
const IS_TEST = import.meta.env.MODE === 'test'

interface RunningScan {
  id: number
  startedAt: number
  options: typeof SCAN_OPTIONS
}

const STORAGE_KEY = 'sqldoc.mock-state'

interface PersistedState {
  scans: ScanSummary[]
  running: RunningScan | null
  nextScanId: number
  annotations: Array<[string, Annotation]>
}

function readPersisted(): PersistedState | null {
  if (IS_TEST || typeof sessionStorage === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as PersistedState) : null
  } catch {
    return null
  }
}

const persisted = readPersisted()
let scans: ScanSummary[] = persisted?.scans ?? INITIAL_SCANS.map((s) => ({ ...s }))
let running: RunningScan | null = persisted?.running ?? null
let nextScanId = persisted?.nextScanId ?? 3
let annotations = new Map<string, Annotation>(persisted?.annotations ?? INITIAL_ANNOTATIONS.map((a) => [a.target_key.toLowerCase(), { ...a }]))

/** Browser mock mode keeps started scans / edited annotations across reloads (sessionStorage). */
function persist(): void {
  if (IS_TEST || typeof sessionStorage === 'undefined') return
  try {
    const state: PersistedState = { scans, running, nextScanId, annotations: [...annotations.entries()] }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    /* ignore quota / privacy errors */
  }
}

/** Reset mutable state between tests. */
export function resetMockState(): void {
  scans = INITIAL_SCANS.map((s) => ({ ...s }))
  running = null
  nextScanId = 3
  annotations = new Map(INITIAL_ANNOTATIONS.map((a) => [a.target_key.toLowerCase(), { ...a }]))
  persist()
}

async function latency(): Promise<void> {
  if (IS_TEST) return
  await delay(90 + Math.random() * 160)
}

function notFound(detail: string) {
  return HttpResponse.json({ detail }, { status: 404 })
}

// ---------------------------------------------------------------------------
// Snapshot helpers
// ---------------------------------------------------------------------------

const BY_ID = new Map(OBJECTS.map((o) => [o.id, o]))

function objectKey(o: FixtureObject): string {
  return o.external
    ? `external|${o.external.server}|${o.external.database}|${o.schema}|${o.name}`
    : `${CONNECTION}|${o.db}|${o.schema}|${o.name}`
}

function isTableStats(s: FixtureObject['stats']): s is TableStats {
  return !!s && 'row_count' in s
}

function isExecStats(s: FixtureObject['stats']): s is ExecStats {
  return !!s && 'exec_count' in s
}

function annotationFor(key: string): Annotation | null {
  return annotations.get(key.toLowerCase()) ?? null
}

function summaryOf(o: FixtureObject): ObjectSummary {
  const ann = annotationFor(objectKey(o))
  return {
    id: o.id,
    object_key: objectKey(o),
    db: o.db,
    schema: o.schema,
    name: o.name,
    kind: o.kind,
    scope: o.scope,
    description: o.description ?? null,
    annotation_description: ann?.description ?? null,
    tags: ann?.tags ?? [],
    row_count: isTableStats(o.stats) ? o.stats.row_count : null,
    total_size_kb: isTableStats(o.stats) ? (o.stats.data_kb ?? 0) + (o.stats.index_kb ?? 0) : null,
    exec_count: isExecStats(o.stats) ? o.stats.exec_count : null,
    modified_at: o.modified_at ?? '2024-02-11T10:14:00Z',
    lineage_status: o.lineage_status ?? 'n/a',
    has_lineage_issues: (o.lineage_issues?.length ?? 0) > 0,
  }
}

function nodeId(id: number): string {
  return `o:${id}`
}

function parseNodeId(id: string | null): number | null {
  if (!id) return null
  const m = /^o:(\d+)$/.exec(id)
  if (m) return Number(m[1])
  const n = Number(id)
  return Number.isFinite(n) ? n : null
}

function qualified(o: FixtureObject): string {
  return `${o.schema}.${o.name}`
}

function refOf(o: FixtureObject): ObjectRefLite {
  return { id: o.id, db: o.db, schema: o.schema, name: o.name, kind: o.kind }
}

// ---------------------------------------------------------------------------
// Object-level lineage (BFS ego graph with hop limits, filters, truncation and `more`)
// ---------------------------------------------------------------------------

interface NodeFilter {
  kinds: Set<string> | null
  schemas: Set<string> | null
  edgeKinds: Set<string> | null
  includeCascaded: boolean
  includeExternal: boolean
}

function passesNode(o: FixtureObject, f: NodeFilter): boolean {
  if (f.kinds && !f.kinds.has(o.kind)) return false
  if (f.schemas && !f.schemas.has(o.schema)) return false
  if (!f.includeCascaded && o.scope === 'cascaded') return false
  if (!f.includeExternal && o.scope === 'external') return false
  return true
}

function neighbours(id: number, dir: 'up' | 'down', f: NodeFilter): number[] {
  return EDGES.filter((e) => (dir === 'up' ? e.target === id : e.source === id))
    .filter((e) => !f.edgeKinds || f.edgeKinds.has(e.kind))
    .map((e) => (dir === 'up' ? e.source : e.target))
    .filter((n) => {
      const o = BY_ID.get(n)
      return !!o && passesNode(o, f)
    })
}

function walk(focus: number, dir: 'up' | 'down', depth: number, f: NodeFilter): Map<number, number> {
  const hops = new Map<number, number>([[focus, 0]])
  let frontier = [focus]
  for (let h = 1; h <= depth && frontier.length; h++) {
    const next: number[] = []
    for (const id of frontier) {
      for (const n of neighbours(id, dir, f)) {
        if (!hops.has(n)) {
          hops.set(n, h)
          next.push(n)
        }
      }
    }
    frontier = next
  }
  return hops
}

function egoGraph(
  focus: number,
  direction: 'up' | 'down' | 'both',
  depth: number,
  f: NodeFilter,
  maxNodes: number,
): LineageGraph {
  const hops = new Map<number, number>([[focus, 0]])
  if (direction !== 'down') for (const [id, h] of walk(focus, 'up', depth, f)) if (!hops.has(id)) hops.set(id, -h)
  if (direction !== 'up') for (const [id, h] of walk(focus, 'down', depth, f)) if (!hops.has(id)) hops.set(id, h)

  const degree = (id: number) => EDGES.filter((e) => e.source === id || e.target === id).length
  const ordered = [...hops.entries()].sort((a, b) => {
    if (a[1] === 0) return -1
    if (b[1] === 0) return 1
    const d = Math.abs(a[1]) - Math.abs(b[1])
    if (d !== 0) return d
    const ea = BY_ID.get(a[0])!.scope === 'external' ? 1 : 0
    const eb = BY_ID.get(b[0])!.scope === 'external' ? 1 : 0
    if (ea !== eb) return ea - eb
    return degree(b[0]) - degree(a[0])
  })
  const kept = ordered.slice(0, maxNodes)
  const keptSet = new Set(kept.map(([id]) => id))

  const nodes: LineageNode[] = kept.map(([id, hop]) => {
    const o = BY_ID.get(id)!
    const s = summaryOf(o)
    return {
      id: nodeId(id),
      object_id: id,
      db: o.db,
      schema: o.schema,
      name: o.name,
      kind: o.kind,
      scope: o.scope,
      hop,
      row_count: s.row_count,
      exec_count: s.exec_count,
      has_lineage_issues: s.has_lineage_issues,
      more: {
        upstream: neighbours(id, 'up', f).filter((n) => !keptSet.has(n)).length,
        downstream: neighbours(id, 'down', f).filter((n) => !keptSet.has(n)).length,
      },
    }
  })

  const edges: LineageEdge[] = EDGES.filter(
    (e) => keptSet.has(e.source) && keptSet.has(e.target) && (!f.edgeKinds || f.edgeKinds.has(e.kind)),
  ).map((e) => ({
    id: `e:${e.source}-${e.target}-${e.kind}`,
    source: nodeId(e.source),
    target: nodeId(e.target),
    kind: e.kind,
    resolution: e.resolution ?? 'resolved',
    detail: e.detail ?? null,
  }))

  return { focus: nodeId(focus), nodes, edges, truncated: hops.size > maxNodes, total: hops.size }
}

// ---------------------------------------------------------------------------
// Column-level lineage
// ---------------------------------------------------------------------------

type ColRef = string // `${objectId}|${column}`
const colRef = (id: number, col: string): ColRef => `${id}|${col}`
const splitRef = (r: ColRef): [number, string] => {
  const i = r.indexOf('|')
  return [Number(r.slice(0, i)), r.slice(i + 1)]
}

function columnGraph(
  focus: number,
  column: string | null,
  direction: 'up' | 'down' | 'both',
  depth: number,
  minConfidence: Confidence,
  maxNodes: number,
): ColumnLineageGraph {
  const min = CONFIDENCE_RANK[minConfidence]
  const edges = COLUMN_EDGES.filter((e) => CONFIDENCE_RANK[e.confidence] >= min)
  const seedCols = column
    ? [colRef(focus, column)]
    : [
        ...new Set(
          edges
            .flatMap((e) => [e.s[0] === focus ? colRef(...e.s) : null, e.t[0] === focus ? colRef(...e.t) : null])
            .filter((x): x is string => !!x),
        ),
      ]
  const visited = new Map<ColRef, number>(seedCols.map((c) => [c, 0]))
  const step = (dir: 'up' | 'down') => {
    let frontier = seedCols
    for (let h = 1; h <= depth && frontier.length; h++) {
      const next: ColRef[] = []
      for (const ref of frontier) {
        const [oid, col] = splitRef(ref)
        for (const e of edges) {
          const match = dir === 'up' ? e.t[0] === oid && e.t[1] === col : e.s[0] === oid && e.s[1] === col
          if (!match) continue
          const other = dir === 'up' ? colRef(...e.s) : colRef(...e.t)
          if (!visited.has(other)) {
            visited.set(other, dir === 'up' ? -h : h)
            next.push(other)
          }
        }
      }
      frontier = next
    }
  }
  if (direction !== 'down') step('up')
  if (direction !== 'up') step('down')

  // group by object
  const byObject = new Map<number, Map<string, number>>()
  for (const [ref, hop] of visited) {
    const [oid, col] = splitRef(ref)
    if (!byObject.has(oid)) byObject.set(oid, new Map())
    byObject.get(oid)!.set(col, hop)
  }
  const ordered = [...byObject.entries()].sort((a, b) => {
    const ha = a[0] === focus ? 0 : Math.min(...[...a[1].values()].map(Math.abs))
    const hb = b[0] === focus ? 0 : Math.min(...[...b[1].values()].map(Math.abs))
    return ha - hb
  })
  const kept = ordered.slice(0, maxNodes)
  const keptSet = new Set(kept.map(([id]) => id))

  const nodes: ColumnLineageNode[] = kept.map(([oid, cols]) => {
    const o = BY_ID.get(oid)!
    const s = summaryOf(o)
    const participating = new Set(cols.keys())
    const ordering = o.columns.length
      ? o.columns.filter((c) => participating.has(c.name)).map((c) => c.name)
      : [...participating]
    const hop = oid === focus ? 0 : [...cols.values()].reduce((a, b) => (Math.abs(a) < Math.abs(b) ? a : b))
    const moreUp = new Set<ColRef>()
    const moreDown = new Set<ColRef>()
    for (const e of edges) {
      if (e.t[0] === oid && participating.has(e.t[1]) && !visited.has(colRef(...e.s))) moreUp.add(colRef(...e.s))
      if (e.s[0] === oid && participating.has(e.s[1]) && !visited.has(colRef(...e.t))) moreDown.add(colRef(...e.t))
    }
    return {
      id: nodeId(oid),
      object_id: oid,
      db: o.db,
      schema: o.schema,
      name: o.name,
      kind: o.kind,
      scope: o.scope,
      hop,
      has_lineage_issues: s.has_lineage_issues,
      more: { upstream: moreUp.size, downstream: moreDown.size },
      columns: ordering.map((name) => {
        const c = o.columns.find((x) => x.name === name)
        return { column_id: c ? o.id * 1000 + o.columns.indexOf(c) : 0, name, data_type: c?.type ?? null }
      }),
      column_count_total: o.columns.length || participating.size,
    }
  })

  const outEdges: ColumnLineageEdge[] = edges
    .filter(
      (e) =>
        keptSet.has(e.s[0]) &&
        keptSet.has(e.t[0]) &&
        visited.has(colRef(...e.s)) &&
        visited.has(colRef(...e.t)),
    )
    .map((e, i) => {
      const via = e.via ? BY_ID.get(e.via) : undefined
      return {
        id: `c:${e.s[0]}.${e.s[1]}->${e.t[0]}.${e.t[1]}#${i}`,
        source: nodeId(e.s[0]),
        source_column: e.s[1],
        target: nodeId(e.t[0]),
        target_column: e.t[1],
        confidence: e.confidence,
        transform: e.transform,
        via_object_id: via?.id ?? null,
        via_name: via ? qualified(via) : null,
        expression: e.expression ?? null,
      }
    })

  return {
    focus: { object_id: focus, column },
    nodes,
    edges: outEdges,
    truncated: byObject.size > maxNodes,
    total: byObject.size,
  }
}

// ---------------------------------------------------------------------------
// Object detail
// ---------------------------------------------------------------------------

function columnsOf(o: FixtureObject): Column[] {
  return o.columns.map((c, i) => {
    const fkTarget = c.fk ? BY_ID.get(c.fk[0]) : undefined
    const colAnn = annotationFor(`${objectKey(o)}|${c.name}`)
    return {
      id: o.id * 1000 + i,
      ordinal: i + 1,
      name: c.name,
      column_kind: o.kind === 'procedure' ? 'resultset' : 'column',
      type_display: c.type,
      is_nullable: c.nullable ?? false,
      is_identity: c.identity ?? false,
      is_computed: !!c.computed,
      computed_definition: c.computed ?? null,
      default_definition: c.default ?? null,
      collation: /char|text/i.test(c.type) ? 'SQL_Latin1_General_CP1_CI_AS' : null,
      in_primary_key: c.pk ?? false,
      fk_to: fkTarget ? { object_id: fkTarget.id, schema: fkTarget.schema, name: fkTarget.name, column: c.fk![1] } : null,
      ms_description: c.desc ?? null,
      description: colAnn?.description ?? null,
      lineage: {
        upstream: COLUMN_EDGES.filter((e) => e.t[0] === o.id && e.t[1] === c.name).length,
        downstream: COLUMN_EDGES.filter((e) => e.s[0] === o.id && e.s[1] === c.name).length,
      },
    }
  })
}

function foreignKey(parent: FixtureObject, columnIndex: number, column: FixtureColumn): ForeignKey {
  const t = BY_ID.get(column.fk![0])!
  return {
    id: parent.id * 100 + columnIndex,
    name: `FK_${parent.name}_${t.name}_${column.name}`,
    parent: refOf(parent),
    referenced: refOf(t),
    columns: [{ column: column.name, referenced_column: column.fk![1] }],
    delete_action: 'NO_ACTION',
    update_action: 'NO_ACTION',
    is_disabled: false,
    is_not_trusted: false,
  }
}

function foreignKeysOut(o: FixtureObject): ForeignKey[] {
  return o.columns.flatMap((c, i) => (c.fk ? [foreignKey(o, i, c)] : []))
}

function foreignKeysIn(o: FixtureObject): ForeignKey[] {
  const out: ForeignKey[] = []
  for (const other of OBJECTS) {
    if (other.id === o.id) continue
    other.columns.forEach((c, i) => {
      if (c.fk && c.fk[0] === o.id) out.push(foreignKey(other, i, c))
    })
  }
  return out
}

function depRef(o: FixtureObject, kind: EdgeKind, resolution: DepRef['resolution']): DepRef {
  return { object_id: o.id, db: o.db, schema: o.schema, name: o.name, kind: o.kind, scope: o.scope, edge_kind: kind, resolution, referenced_name: o.name }
}

function detailOf(o: FixtureObject): ObjectDetail {
  const parent = o.parent_id ? BY_ID.get(o.parent_id) : undefined
  const pk = o.columns.filter((c) => c.pk).map((c) => c.name)
  const colAnns: Record<string, Annotation> = {}
  for (const c of o.columns) {
    const a = annotationFor(`${objectKey(o)}|${c.name}`)
    if (a) colAnns[c.name] = a
  }
  const all: NodeFilter = { kinds: null, schemas: null, edgeKinds: null, includeCascaded: true, includeExternal: true }
  return {
    summary: summaryOf(o),
    sql_object_id: o.external ? null : 100_000 + o.id * 37,
    ms_description: o.description ?? null,
    created_at: o.created_at ?? '2017-10-27T14:33:00Z',
    modified_at: o.modified_at ?? '2024-02-11T10:14:00Z',
    parent: parent ? { id: parent.id, schema: parent.schema, name: parent.name, kind: parent.kind } : null,
    definition_length: o.definition?.length ?? 0,
    has_dynamic_sql: o.has_dynamic_sql ?? false,
    is_schema_bound: o.kind === 'scalar_function' ? true : null,
    trigger_events: o.trigger ? o.trigger.events.join(', ') : null,
    is_instead_of_trigger: o.trigger?.is_instead_of ?? null,
    is_disabled: o.trigger?.is_disabled ?? null,
    external_server: o.external?.server ?? null,
    columns: columnsOf(o),
    parameters: o.params ?? [],
    indexes: o.indexes ?? [],
    keys: {
      primary_key: pk.length ? { name: `PK_${o.name}_${pk.join('_')}`, type_desc: 'CLUSTERED', columns: pk } : null,
      unique_constraints: (o.indexes ?? [])
        .filter((i) => i.is_unique_constraint)
        .map((i) => ({ name: i.name, type_desc: i.type_desc, columns: (i.key_columns ?? []).map((k) => k.name) })),
      foreign_keys_out: foreignKeysOut(o),
      foreign_keys_in: foreignKeysIn(o),
      check_constraints: o.checks ?? [],
    },
    triggers: OBJECTS.filter((t) => t.kind === 'trigger' && t.parent_id === o.id).map((t) => ({
      id: t.id,
      name: t.name,
      events: t.trigger?.events.join(', ') ?? null,
      is_instead_of: t.trigger?.is_instead_of ?? false,
      is_disabled: t.trigger?.is_disabled ?? false,
    })),
    stats: o.stats ?? null,
    missing_indexes: o.missing_indexes ?? [],
    dependencies: {
      uses: EDGES.filter((e) => e.target === o.id).map((e) => depRef(BY_ID.get(e.source)!, e.kind, e.resolution ?? 'resolved')),
      used_by: EDGES.filter((e) => e.source === o.id).map((e) => depRef(BY_ID.get(e.target)!, e.kind, e.resolution ?? 'resolved')),
    },
    lineage_counts: {
      upstream: walk(o.id, 'up', 5, all).size - 1,
      downstream: walk(o.id, 'down', 5, all).size - 1,
      columns_with_lineage: new Set(
        COLUMN_EDGES.flatMap((e) => [e.s[0] === o.id ? e.s[1] : null, e.t[0] === o.id ? e.t[1] : null]).filter(Boolean),
      ).size,
    },
    lineage_issues: o.lineage_issues ?? [],
    annotation: annotationFor(objectKey(o)),
    column_annotations: colAnns,
  }
}

// ---------------------------------------------------------------------------
// Scans
// ---------------------------------------------------------------------------

function progressFor(r: RunningScan, now: number): { progress: ScanProgress; done: boolean } {
  // phase names are the contract's ScanPhase enum
  const elapsed = now - r.startedAt
  const phaseIndex = Math.min(SCAN_PHASES.length, Math.floor(elapsed / PHASE_MS))
  const done = phaseIndex >= SCAN_PHASES.length
  const phase: ScanPhase = SCAN_PHASES[Math.min(phaseIndex, SCAN_PHASES.length - 1)]!
  const within = (elapsed % PHASE_MS) / PHASE_MS
  const totals: Record<string, number> = { connect: 1, enumerate: 3, cascade: 1, extract: 29, stats: 4, lineage: 11, finalize: 1 }
  const total = totals[phase] ?? 1
  const current = done ? total : Math.min(total, Math.max(1, Math.round(within * total)))
  const messages: Record<string, string> = {
    connect: 'Connected to localhost:1433 (SQL Server 2022, auth_scheme=SQL)',
    enumerate: `Enumerating ${DB}: ${current}/${total} catalog queries`,
    cascade: 'Computing closure for [Sales, dbo] — 22 seed objects, 11 cascaded',
    extract: `Extracting ${DB}: object ${current}/${total}`,
    stats: `Collecting stats (${current}/${total}): table_stats, index_usage, proc_stats, missing_indexes`,
    lineage: `Parsing T-SQL (${current}/${total}): ${['Sales.vIndividualCustomer', 'Sales.vSalesQuota', 'Sales.vSalesOrderSummary', 'Sales.vSalesPerson', 'dbo.ufnGetContactInformation', 'dbo.uspGetBillOfMaterials', 'dbo.uspLogError', 'dbo.uspPrintError', 'Sales.iduSalesOrderDetail', 'dbo.ufnLeadingZeros', 'computed columns'][Math.min(10, current - 1)]}`,
    finalize: 'Writing summary',
  }
  return {
    done,
    progress: {
      phase: done ? 'finalize' : phase,
      phase_index: Math.min(phaseIndex, SCAN_PHASES.length - 1),
      phase_count: SCAN_PHASES.length,
      current,
      total,
      message: done ? 'Scan complete' : messages[phase],
      updated_at: new Date(now).toISOString(),
    },
  }
}

function settleRunning(): void {
  if (!running) return
  const now = Date.now()
  const { done } = progressFor(running, now)
  if (!done) return
  const finished: ScanSummary = {
    id: running.id,
    connection: CONNECTION,
    status: 'succeeded',
    started_at: new Date(running.startedAt).toISOString(),
    finished_at: new Date(now).toISOString(),
    duration_ms: now - running.startedAt,
    options: running.options,
    counts: SCAN_COUNTS,
  }
  scans = [finished, ...scans.filter((s) => s.id !== running!.id)]
  running = null
  persist()
}

function scanDetail(id: number): ScanDetail | null {
  settleRunning()
  if (running && running.id === id) {
    const { progress } = progressFor(running, Date.now())
    return {
      id,
      connection: CONNECTION,
      status: 'running',
      started_at: new Date(running.startedAt).toISOString(),
      finished_at: null,
      duration_ms: null,
      options: running.options,
      counts: EMPTY_COUNTS,
      progress,
      warnings: [],
      log: [],
    }
  }
  const s = scans.find((x) => x.id === id)
  if (!s) return null
  return {
    ...s,
    progress: {
      phase: 'finalize',
      phase_index: SCAN_PHASES.length - 1,
      phase_count: SCAN_PHASES.length,
      current: 1,
      total: 1,
      message: s.status === 'succeeded' ? 'Scan complete' : (s.error ?? 'Scan failed'),
      updated_at: s.finished_at ?? s.started_at,
    },
    warnings:
      s.status === 'succeeded'
        ? [
            { phase: 'stats', database: DB, code: 'stats_unavailable', message: 'missing_indexes: VIEW SERVER STATE not granted; missing-index suggestions limited to cached plans.' },
            { phase: 'lineage', database: DB, code: 'lineage_issue', message: '2 objects produced lineage issues (dbo.uspGetBillOfMaterials, Sales.vSalesQuota).' },
          ]
        : [],
    log: [],
  }
}

function latestScan(): ScanSummary | null {
  settleRunning()
  return scans.find((s) => s.status === 'succeeded') ?? null
}

function snapshotExists(id: number): boolean {
  settleRunning()
  return scans.some((s) => s.id === id && s.status === 'succeeded')
}

// ---------------------------------------------------------------------------
// Listing helpers
// ---------------------------------------------------------------------------

function paged<T>(items: T[], url: URL, defaultLimit = 50): Paged<T> {
  const limit = Math.max(1, Math.min(500, Number(url.searchParams.get('limit') ?? defaultLimit)))
  const offset = Math.max(0, Number(url.searchParams.get('offset') ?? 0))
  return { items: items.slice(offset, offset + limit), total: items.length, limit, offset }
}

function sortBy<T>(items: T[], key: (t: T) => string | number | null | undefined, order: string | null): T[] {
  const dir = order === 'desc' ? -1 : 1
  return [...items].sort((a, b) => {
    const ka = key(a)
    const kb = key(b)
    if (ka == null && kb == null) return 0
    if (ka == null) return 1
    if (kb == null) return -1
    if (typeof ka === 'number' && typeof kb === 'number') return (ka - kb) * dir
    return String(ka).localeCompare(String(kb), undefined, { sensitivity: 'base' }) * dir
  })
}

function scanIdParam(params: Record<string, string | readonly string[] | undefined>): number {
  return Number(params.id)
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export const handlers = [
  http.get('/api/health', async () => {
    await latency()
    return HttpResponse.json({ ok: true, version: '0.1.0-mock', db_path: '/Users/me/repos/SQLDocumentor/sqldoc.sqlite' })
  }),

  http.get('/api/config', async () => {
    await latency()
    return HttpResponse.json({
      config_path: '/Users/me/repos/SQLDocumentor/sqldoc.yaml',
      sqlite_path: '/Users/me/repos/SQLDocumentor/sqldoc.sqlite',
      config: {
        version: 1,
        storage: { sqlite_path: './sqldoc.sqlite' },
        connections: [
          {
            name: CONNECTION,
            host: 'localhost',
            port: 1433,
            auth: { mode: 'sql', username: 'sa', password: '**********' },
            driver: 'auto',
            encrypt: true,
            trust_server_certificate: true,
            databases: [{ name: DB, schemas: SELECTED_SCHEMAS }],
          },
        ],
        scan: SCAN_OPTIONS,
      },
    })
  }),

  http.get('/api/connections', async () => {
    await latency()
    settleRunning()
    return HttpResponse.json({
      items: [
        {
          name: CONNECTION,
          host: 'localhost',
          port: 1433,
          auth_mode: 'sql',
          username: 'sa',
          driver: 'auto',
          databases: [{ name: DB, schemas: SELECTED_SCHEMAS }],
          latest_scan: latestScan(),
          running_scan_id: running?.id ?? null,
        },
      ],
    })
  }),

  http.post('/api/connections/:name/test', async ({ params }) => {
    await delay(IS_TEST ? 0 : 900)
    if (params.name !== CONNECTION) return notFound('Connection not found')
    return HttpResponse.json({
      ok: true,
      server_name: 'mssql',
      version: '16.0.4165.4',
      edition: 'Developer Edition (64-bit)',
      auth_scheme: 'SQL',
      driver: 'ODBC Driver 18 for SQL Server',
      can_view_server_state: true,
      databases: [{ name: DB, reachable: true, can_view_definition: true, can_view_database_state: true }],
    })
  }),

  http.get('/api/connections/:name/scans', async ({ params, request }) => {
    await latency()
    if (params.name !== CONNECTION) return notFound('Connection not found')
    settleRunning()
    const items: ScanSummary[] = running
      ? [
          {
            id: running.id,
            connection: CONNECTION,
            status: 'running',
            started_at: new Date(running.startedAt).toISOString(),
            finished_at: null,
            duration_ms: null,
            options: running.options,
            counts: EMPTY_COUNTS,
          },
          ...scans,
        ]
      : scans
    return HttpResponse.json(paged(items, new URL(request.url), 20))
  }),

  http.post('/api/connections/:name/scans', async ({ params, request }) => {
    await latency()
    if (params.name !== CONNECTION) return notFound('Connection not found')
    settleRunning()
    if (running) return HttpResponse.json({ detail: 'A scan is already running for this connection' }, { status: 409 })
    const body = ((await request.json().catch(() => ({}))) ?? {}) as { collect_stats?: boolean | null; parse_lineage?: boolean | null }
    running = {
      id: nextScanId++,
      startedAt: Date.now(),
      options: { ...SCAN_OPTIONS, collect_stats: body.collect_stats ?? true, parse_lineage: body.parse_lineage ?? true },
    }
    persist()
    return HttpResponse.json({ scan_id: running.id }, { status: 202 })
  }),

  http.get('/api/scans/:id', async ({ params }) => {
    await latency()
    const d = scanDetail(scanIdParam(params))
    return d ? HttpResponse.json(d) : notFound('Scan not found')
  }),

  http.post('/api/scans/:id/cancel', async ({ params }) => {
    await latency()
    settleRunning()
    const id = scanIdParam(params)
    if (running && running.id === id) {
      const now = Date.now()
      scans = [
        {
          id,
          connection: CONNECTION,
          status: 'cancelled',
          started_at: new Date(running.startedAt).toISOString(),
          finished_at: new Date(now).toISOString(),
          duration_ms: now - running.startedAt,
          options: running.options,
          counts: EMPTY_COUNTS,
        },
        ...scans,
      ]
      running = null
      persist()
      return HttpResponse.json({ scan_id: id, cancelled: true })
    }
    return HttpResponse.json({ detail: 'Scan is not running' }, { status: 409 })
  }),

  http.delete('/api/scans/:id', async ({ params }) => {
    await latency()
    const id = scanIdParam(params)
    if (!scans.some((s) => s.id === id)) return notFound('Scan not found')
    scans = scans.filter((s) => s.id !== id)
    persist()
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/scans/:id/summary', async ({ params }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const schemaNames = [...new Set(OBJECTS.filter((o) => !o.external).map((o) => o.schema))].sort()
    const summary: SnapshotSummary = {
      databases: [
        {
          name: DB,
          is_configured: true,
          schemas: schemaNames.map((name) => {
            const counts: Partial<Record<ObjectKind, number>> = {}
            for (const o of OBJECTS) if (o.schema === name && !o.external) counts[o.kind] = (counts[o.kind] ?? 0) + 1
            return { name, is_selected: SELECTED_SCHEMAS.includes(name), counts_by_kind: counts }
          }),
        },
      ],
      counts: SCAN_COUNTS,
      lineage_coverage: 0.86,
      warnings_summary: {
        lineage_issues: OBJECTS.reduce((n, o) => n + (o.lineage_issues?.length ?? 0), 0),
        unused_indexes: OBJECTS.reduce((n, o) => n + (o.indexes ?? []).filter((i) => i.is_unused).length, 0),
        missing_index_suggestions: OBJECTS.reduce((n, o) => n + (o.missing_indexes?.length ?? 0), 0),
        external_refs: OBJECTS.filter((o) => o.scope === 'external').length,
      },
    }
    return HttpResponse.json(summary)
  }),

  http.get('/api/scans/:id/objects', async ({ params, request }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const url = new URL(request.url)
    const q = url.searchParams
    let items = OBJECTS.map(summaryOf)
    const db = q.get('db')
    const schema = q.get('schema')
    const kind = q.get('kind')
    const scope = q.get('scope')
    const text = q.get('q')?.toLowerCase()
    const tag = q.get('tag')
    const hasIssues = q.get('has_issues')
    if (db) items = items.filter((o) => (o.db ?? '').toLowerCase() === db.toLowerCase())
    if (schema) items = items.filter((o) => (o.schema ?? '').toLowerCase() === schema.toLowerCase())
    if (kind) {
      const kinds = new Set(kind.split(','))
      items = items.filter((o) => kinds.has(o.kind))
    }
    if (scope) items = items.filter((o) => o.scope === scope)
    if (text) items = items.filter((o) => `${o.schema}.${o.name}`.toLowerCase().includes(text))
    if (tag) items = items.filter((o) => (o.tags ?? []).includes(tag))
    if (hasIssues === 'true') items = items.filter((o) => o.has_lineage_issues)
    const sort = q.get('sort') ?? 'name'
    const order = q.get('order')
    const keyFn: Record<string, (o: ObjectSummary) => string | number | null | undefined> = {
      name: (o) => `${o.schema}.${o.name}`,
      kind: (o) => `${o.kind}|${o.schema}.${o.name}`,
      rows: (o) => o.row_count,
      size: (o) => o.total_size_kb,
      modified: (o) => o.modified_at,
    }
    items = sortBy(items, keyFn[sort] ?? keyFn.name, order)
    return HttpResponse.json(paged(items, url))
  }),

  http.get('/api/scans/:id/objects/lookup', async ({ params, request }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const q = new URL(request.url).searchParams
    const db = q.get('db')?.toLowerCase()
    const schema = q.get('schema')?.toLowerCase()
    const name = q.get('name')?.toLowerCase()
    const o = OBJECTS.find(
      (x) => (!db || x.db.toLowerCase() === db) && x.schema.toLowerCase() === schema && x.name.toLowerCase() === name,
    )
    return o ? HttpResponse.json(detailOf(o)) : notFound('Object not found in this scan')
  }),

  http.get('/api/scans/:id/objects/:object_id', async ({ params }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const o = BY_ID.get(Number(params.object_id))
    return o ? HttpResponse.json(detailOf(o)) : notFound('Object not found in this scan')
  }),

  http.get('/api/scans/:id/objects/:object_id/definition', async ({ params }) => {
    await delay(IS_TEST ? 0 : 200)
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const o = BY_ID.get(Number(params.object_id))
    if (!o) return notFound('Object not found in this scan')
    return HttpResponse.json({ definition: o.definition ?? null, length: o.definition?.length ?? 0, has_dynamic_sql: o.has_dynamic_sql ?? false })
  }),

  http.get('/api/scans/:id/search', async ({ params, request }) => {
    await delay(IS_TEST ? 0 : 60)
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const q = new URL(request.url).searchParams
    const text = (q.get('q') ?? '').trim().toLowerCase()
    const limit = Number(q.get('limit') ?? 20)
    const kinds = new Set((q.get('kinds') ?? 'object,column').split(','))
    const objects: SearchObjectHit[] = []
    const columns: SearchColumnHit[] = []
    const result: SearchResult = { objects, columns }
    if (!text) return HttpResponse.json(result)
    if (kinds.has('object')) {
      objects.push(...OBJECTS.filter((o) => `${o.schema}.${o.name}`.toLowerCase().includes(text) || o.description?.toLowerCase().includes(text))
        .slice(0, limit)
        .map((o) => ({
          ...summaryOf(o),
          match: `${o.schema}.${o.name}`.toLowerCase().includes(text)
            ? { field: 'name', snippet: `${o.schema}.${o.name}` }
            : { field: 'description', snippet: o.description ?? '' },
        })))
    }
    if (kinds.has('column')) {
      for (const o of OBJECTS) {
        for (const c of o.columns) {
          if (c.name.toLowerCase().includes(text)) columns.push({ object: summaryOf(o), column: c.name, data_type: c.type })
          if (columns.length >= limit) break
        }
        if (columns.length >= limit) break
      }
    }
    return HttpResponse.json(result)
  }),

  http.get('/api/scans/:id/lineage/objects', async ({ params, request }) => {
    await delay(IS_TEST ? 0 : 220)
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const q = new URL(request.url).searchParams
    const focus = parseNodeId(q.get('focus'))
    if (focus == null || !BY_ID.has(focus)) return notFound('Focus object not found')
    const dirRaw = q.get('direction')
    const direction = dirRaw === 'up' || dirRaw === 'down' ? dirRaw : 'both'
    const depth = Math.min(5, Math.max(1, Number(q.get('depth') ?? 2)))
    const csv = (k: string) => {
      const v = q.get(k)
      return v ? new Set(v.split(',').filter(Boolean)) : null
    }
    const f: NodeFilter = {
      kinds: csv('kinds'),
      schemas: csv('schemas'),
      edgeKinds: csv('edge_kinds'),
      includeCascaded: q.get('include_cascaded') !== 'false',
      includeExternal: q.get('include_external') !== 'false',
    }
    const maxNodes = Math.min(1000, Math.max(1, Number(q.get('max_nodes') ?? 200)))
    return HttpResponse.json(egoGraph(focus, direction, depth, f, maxNodes))
  }),

  http.get('/api/scans/:id/lineage/columns', async ({ params, request }) => {
    await delay(IS_TEST ? 0 : 260)
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const q = new URL(request.url).searchParams
    const focus = parseNodeId(q.get('focus'))
    if (focus == null || !BY_ID.has(focus)) return notFound('Focus object not found')
    const dirRaw = q.get('direction')
    const direction = dirRaw === 'up' || dirRaw === 'down' ? dirRaw : 'both'
    const depth = Math.min(5, Math.max(1, Number(q.get('depth') ?? 2)))
    const mc = q.get('min_confidence')
    const minConfidence: Confidence = mc === 'exact' || mc === 'inferred' ? mc : 'unresolved'
    const maxNodes = Math.min(1000, Math.max(1, Number(q.get('max_nodes') ?? 150)))
    return HttpResponse.json(columnGraph(focus, q.get('column') || null, direction, depth, minConfidence, maxNodes))
  }),

  http.get('/api/scans/:id/lineage/objects/:object_id/columns', async ({ params }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const o = BY_ID.get(Number(params.object_id))
    if (!o) return notFound('Object not found in this scan')
    const rows = o.columns
      .map((c, i) => {
        const up = COLUMN_EDGES.filter((e) => e.t[0] === o.id && e.t[1] === c.name)
        const down = COLUMN_EDGES.filter((e) => e.s[0] === o.id && e.s[1] === c.name)
        const conf = { exact: 0, inferred: 0, unresolved: 0 }
        for (const e of [...up, ...down]) conf[e.confidence]++
        return { column_id: o.id * 1000 + i, name: c.name, upstream_count: up.length, downstream_count: down.length, confidences: conf }
      })
      .filter((r) => r.upstream_count + r.downstream_count > 0)
    return HttpResponse.json(rows)
  }),

  http.get('/api/scans/:id/lineage/summary', async ({ params }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const byKind: Partial<Record<EdgeKind, number>> = {}
    for (const e of EDGES) byKind[e.kind] = (byKind[e.kind] ?? 0) + 1
    const byConf: Partial<Record<Confidence, number>> = {}
    for (const e of COLUMN_EDGES) byConf[e.confidence] = (byConf[e.confidence] ?? 0) + 1
    const degree = new Map<number, number>()
    for (const e of EDGES) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1)
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1)
    }
    return HttpResponse.json({
      objects: OBJECTS.length,
      edges_by_kind: byKind,
      column_edges_by_confidence: byConf,
      lineage_coverage: 0.86,
      objects_with_issues: OBJECTS.filter((o) => o.lineage_issues?.length).length,
      top_hubs: [...degree.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([id, d]): LineageHub => {
          const o = BY_ID.get(id)!
          return {
            object_id: id,
            db: o.db,
            schema: o.schema,
            name: o.name,
            kind: o.kind,
            upstream: EDGES.filter((e) => e.target === id).length,
            downstream: EDGES.filter((e) => e.source === id).length,
            degree: d,
          }
        }),
    })
  }),

  http.get('/api/scans/:id/lineage/issues', async ({ params, request }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const rows = OBJECTS.flatMap((o) => (o.lineage_issues ?? []).map((i, n) => ({ ...i, id: o.id * 10 + n, object: refOf(o) })))
    return HttpResponse.json(paged(rows, new URL(request.url)))
  }),

  http.get('/api/scans/:id/stats/tables', async ({ params, request }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const url = new URL(request.url)
    let rows: TableStatsRow[] = OBJECTS.filter((o) => isTableStats(o.stats)).map((o) => {
      const t = o.stats as TableStats
      return { object: summaryOf(o), row_count: t.row_count, data_kb: t.data_kb, index_kb: t.index_kb, reserved_kb: t.reserved_kb, partition_count: t.partition_count, is_heap: t.is_heap, compression: t.compression }
    })
    const schema = url.searchParams.get('schema')
    if (schema) rows = rows.filter((r) => r.object.schema === schema)
    const sort = url.searchParams.get('sort') ?? 'reserved_kb'
    const keys: Record<string, (r: TableStatsRow) => number | string | null | undefined> = {
      name: (r) => `${r.object.schema}.${r.object.name}`,
      rows: (r) => r.row_count,
      data_kb: (r) => r.data_kb,
      index_kb: (r) => r.index_kb,
      reserved_kb: (r) => r.reserved_kb,
      size: (r) => r.reserved_kb,
      partitions: (r) => r.partition_count,
    }
    rows = sortBy(rows, keys[sort] ?? keys.reserved_kb, url.searchParams.get('order') ?? 'desc')
    return HttpResponse.json(paged(rows, url))
  }),

  http.get('/api/scans/:id/stats/indexes', async ({ params, request }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const url = new URL(request.url)
    let rows: IndexStatsRow[] = OBJECTS.flatMap((o) =>
      (o.indexes ?? []).map((i) => ({
        object: summaryOf(o),
        index_id: i.id,
        index_name: i.name,
        type_desc: i.type_desc,
        is_unique: i.is_unique,
        is_primary_key: i.is_primary_key,
        is_unique_constraint: i.is_unique_constraint,
        key_columns: (i.key_columns ?? []).map((k) => k.name),
        included_columns: i.included_columns ?? [],
        seeks: i.usage?.seeks ?? 0,
        scans: i.usage?.scans ?? 0,
        lookups: i.usage?.lookups ?? 0,
        updates: i.usage?.updates ?? 0,
        last_seek: i.usage?.last_seek ?? null,
        last_scan: i.usage?.last_scan ?? null,
        last_lookup: i.usage?.last_lookup ?? null,
        last_update: i.usage?.last_update ?? null,
        is_unused: i.is_unused,
      })),
    )
    if (url.searchParams.get('unused') === 'true') rows = rows.filter((r) => r.is_unused)
    const sort = url.searchParams.get('sort') ?? 'updates'
    const keys: Record<string, (r: IndexStatsRow) => number | string | null | undefined> = {
      name: (r) => `${r.object.schema}.${r.object.name}.${r.index_name}`,
      table: (r) => `${r.object.schema}.${r.object.name}`,
      seeks: (r) => r.seeks,
      scans: (r) => r.scans,
      lookups: (r) => r.lookups,
      updates: (r) => r.updates,
    }
    rows = sortBy(rows, keys[sort] ?? keys.updates, url.searchParams.get('order') ?? 'desc')
    return HttpResponse.json(paged(rows, url))
  }),

  http.get('/api/scans/:id/stats/procs', async ({ params, request }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const url = new URL(request.url)
    let rows: ProcStatsRow[] = OBJECTS.filter((o) => isExecStats(o.stats)).map((o) => {
      const x = o.stats as ExecStats
      return { object: summaryOf(o), exec_count: x.exec_count, total_ms: x.total_ms, avg_ms: x.avg_ms, min_ms: x.min_ms, max_ms: x.max_ms, total_cpu_ms: x.total_cpu_ms, total_logical_reads: x.total_logical_reads, last_exec_at: x.last_exec_at, cached_since: x.cached_since }
    })
    const sort = url.searchParams.get('sort') ?? 'total_ms'
    const keys: Record<string, (r: ProcStatsRow) => number | string | null | undefined> = {
      name: (r) => `${r.object.schema}.${r.object.name}`,
      exec_count: (r) => r.exec_count,
      total_ms: (r) => r.total_ms,
      avg_ms: (r) => r.avg_ms,
      max_ms: (r) => r.max_ms,
      cpu: (r) => r.total_cpu_ms,
      reads: (r) => r.total_logical_reads,
      last_exec: (r) => r.last_exec_at,
    }
    rows = sortBy(rows, keys[sort] ?? keys.total_ms, url.searchParams.get('order') ?? 'desc')
    return HttpResponse.json(paged(rows, url))
  }),

  http.get('/api/scans/:id/stats/missing-indexes', async ({ params, request }) => {
    await latency()
    if (!snapshotExists(scanIdParam(params))) return notFound('Scan not found')
    const url = new URL(request.url)
    let rows: MissingIndexRow[] = OBJECTS.flatMap((o) => (o.missing_indexes ?? []).map((m) => ({ ...m, object: summaryOf(o) })))
    const sort = url.searchParams.get('sort') ?? 'improvement'
    const keys: Record<string, (r: MissingIndexRow) => number | string | null | undefined> = {
      improvement: (r) => r.improvement_measure,
      seeks: (r) => r.user_seeks,
      impact: (r) => r.avg_impact,
      cost: (r) => r.avg_cost,
      name: (r) => `${r.object.schema}.${r.object.name}`,
    }
    rows = sortBy(rows, keys[sort] ?? keys.improvement, url.searchParams.get('order') ?? 'desc')
    return HttpResponse.json(paged(rows, url))
  }),

  // ---- annotations & tags --------------------------------------------------

  http.get('/api/annotations', async ({ request }) => {
    await latency()
    const q = new URL(request.url).searchParams
    const tag = q.get('tag')
    const text = q.get('q')?.toLowerCase()
    let items: Annotation[] = [...annotations.values()].map((a) => {
      const parts = a.target_key.split('|')
      return { ...a, connection: parts[0], db: parts[1], schema: parts[2], name: parts[3], column: parts[4] ?? null }
    })
    if (tag) items = items.filter((a) => (a.tags ?? []).includes(tag))
    if (text) items = items.filter((a) => a.target_key.toLowerCase().includes(text) || a.description?.toLowerCase().includes(text) || a.notes?.toLowerCase().includes(text))
    return HttpResponse.json(paged(items, new URL(request.url)))
  }),

  http.put('/api/annotations', async ({ request }) => {
    await latency()
    const body = (await request.json()) as AnnotationUpsert
    const key = [body.connection, body.db, body.schema, body.name, ...(body.column ? [body.column] : [])].join('|')
    const existing = annotationFor(key)
    const next: Annotation = {
      target_kind: body.column ? 'column' : 'object',
      target_key: key,
      connection: body.connection,
      db: body.db,
      schema: body.schema,
      name: body.name,
      column: body.column ?? null,
      description: body.description === undefined ? (existing?.description ?? null) : body.description,
      notes: body.notes === undefined ? (existing?.notes ?? null) : body.notes,
      tags: body.tags === undefined ? (existing?.tags ?? []) : (body.tags ?? []),
      updated_at: new Date().toISOString(),
    }
    annotations.set(key.toLowerCase(), next)
    persist()
    return HttpResponse.json(next)
  }),

  http.delete('/api/annotations', async ({ request }) => {
    await latency()
    const url = new URL(request.url)
    const k = {
      connection: url.searchParams.get('connection') ?? '',
      db: url.searchParams.get('db') ?? '',
      schema: url.searchParams.get('schema') ?? '',
      name: url.searchParams.get('name') ?? '',
      column: url.searchParams.get('column'),
    }
    const key = [k.connection, k.db, k.schema, k.name, ...(k.column ? [k.column] : [])].join('|').toLowerCase()
    annotations.delete(key)
    persist()
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/tags', async () => {
    await latency()
    const counts = new Map<string, number>()
    for (const a of annotations.values()) for (const t of a.tags ?? []) counts.set(t, (counts.get(t) ?? 0) + 1)
    const tags: Tag[] = [...counts.entries()].sort().map(([tag, count]) => ({ tag, color: TAG_COLORS[tag] ?? null, count }))
    return HttpResponse.json(tags)
  }),
]
