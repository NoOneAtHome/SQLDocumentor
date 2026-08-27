import { useQueries } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { $api, scanPath } from '@/api/client'
import type { ObjectKind, ObjectSummary } from '@/api/types'
import { useScanContext } from '@/app/scan-context'
import { OBJECT_KINDS, SNAPSHOT_QUERY } from '@/lib/constants'
import { routes } from '@/lib/routes'
import { ObjectTreeNode, type TreeRow } from './ObjectTreeNode'

const TREE_PAGE = 400
const ROW_H = 28

function kindId(db: string, schema: string, kind: string) {
  return `k:${db}|${schema}|${kind}`
}

/**
 * Lazy, virtualised object tree: db → schema → kind (with counts) → objects.
 * Each kind group fetches its objects only when expanded. The current route's db/schema/kind/name
 * are auto-expanded so deep links land on a visible, highlighted node.
 */
export function ObjectTree() {
  const { scanId, summary } = useScanContext()
  const params = useParams()
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())

  // Auto-expand the path to the current object.
  useEffect(() => {
    const { db, schema, kind } = params
    if (!db) return
    setExpanded((prev) => {
      const next = new Set(prev)
      next.add(`d:${db}`)
      if (schema) next.add(`s:${db}|${schema}`)
      if (schema && kind) next.add(kindId(db, schema, kind))
      return next
    })
  }, [params])

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // Which kind groups need object lists?
  const openKinds = useMemo(() => {
    const out: Array<{ db: string; schema: string; kind: ObjectKind }> = []
    for (const db of summary.databases)
      for (const s of db.schemas)
        for (const kind of OBJECT_KINDS)
          if ((s.counts_by_kind[kind] ?? 0) > 0 && expanded.has(kindId(db.name, s.name, kind))) out.push({ db: db.name, schema: s.name, kind })
    return out
  }, [summary, expanded])

  const objectQueries = useQueries({
    queries: openKinds.map((k) =>
      $api.queryOptions(
        'get',
        '/api/scans/{scan_id}/objects',
        { params: { path: scanPath(scanId), query: { db: k.db, schema: k.schema, kind: k.kind, sort: 'name', limit: TREE_PAGE } } },
        SNAPSHOT_QUERY,
      ),
    ),
  })
  const objectsByKind = useMemo(() => {
    const m = new Map<string, { items: ObjectSummary[]; total: number; loading: boolean }>()
    openKinds.forEach((k, i) => {
      const q = objectQueries[i]!
      m.set(kindId(k.db, k.schema, k.kind), { items: q.data?.items ?? [], total: q.data?.total ?? 0, loading: q.isPending })
    })
    return m
  }, [openKinds, objectQueries])

  const rows = useMemo<TreeRow[]>(() => {
    const out: TreeRow[] = []
    for (const db of summary.databases) {
      const dbId = `d:${db.name}`
      const dbOpen = expanded.has(dbId)
      const dbCount = db.schemas.reduce((n, s) => n + Object.values(s.counts_by_kind).reduce((a, b) => a + (b ?? 0), 0), 0)
      out.push({ type: 'db', id: dbId, db: db.name, depth: 0, expanded: dbOpen, count: dbCount, to: routes.db(scanId, db.name) })
      if (!dbOpen) continue
      for (const s of db.schemas) {
        const sId = `s:${db.name}|${s.name}`
        const sOpen = expanded.has(sId)
        const sCount = Object.values(s.counts_by_kind).reduce((a, b) => a + (b ?? 0), 0)
        out.push({ type: 'schema', id: sId, db: db.name, schema: s.name, depth: 1, expanded: sOpen, count: sCount, selected: s.is_selected, to: routes.schema(scanId, db.name, s.name) })
        if (!sOpen) continue
        for (const kind of OBJECT_KINDS) {
          const count = s.counts_by_kind[kind] ?? 0
          if (!count) continue
          const kId = kindId(db.name, s.name, kind)
          const kOpen = expanded.has(kId)
          const data = objectsByKind.get(kId)
          out.push({ type: 'kind', id: kId, db: db.name, schema: s.name, kind, depth: 2, expanded: kOpen, count, loading: !!data?.loading, to: routes.kindList(scanId, db.name, s.name, kind) })
          if (!kOpen || !data) continue
          for (const o of data.items)
            out.push({ type: 'object', id: `o:${o.id}`, db: o.db ?? db.name, schema: o.schema ?? s.name, kind: o.kind, name: o.name, depth: 3, to: routes.object(scanId, o), scope: o.scope, hasIssues: o.has_lineage_issues })
          if (data.total > data.items.length) out.push({ type: 'more', id: `${kId}:more`, depth: 3, count: data.total - data.items.length, to: routes.kindList(scanId, db.name, s.name, kind) })
        }
      }
    }
    return out
  }, [summary, expanded, objectsByKind, scanId])

  const scrollRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 16,
    getItemKey: (i) => rows[i]!.id,
  })

  const activeId = params.name ? `${params.db}|${params.schema}|${params.name}`.toLowerCase() : null
  const isActive = (row: TreeRow) => {
    if (row.type === 'object') return `${row.db}|${row.schema}|${row.name}`.toLowerCase() === activeId
    if (row.type === 'schema') return !params.name && !params.kind && params.schema === row.schema && params.db === row.db
    if (row.type === 'db') return !params.schema && params.db === row.db
    if (row.type === 'kind') return !params.name && params.kind === row.kind && params.schema === row.schema
    return false
  }

  // Keep the active row in view when navigating.
  useEffect(() => {
    if (!activeId) return
    const idx = rows.findIndex((r) => r.type === 'object' && `${r.db}|${r.schema}|${r.name}`.toLowerCase() === activeId)
    if (idx >= 0) virtualizer.scrollToIndex(idx, { align: 'auto' })
  }, [activeId, rows, virtualizer])

  return (
    <div ref={scrollRef} className="no-scrollbar h-full min-h-0 overflow-auto px-1.5 pb-2" role="tree" aria-label="Object tree">
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((item) => {
          const row = rows[item.index]!
          return (
            <div key={item.key} data-index={item.index} ref={virtualizer.measureElement} role="treeitem" aria-level={row.depth + 1} style={{ position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${item.start}px)` }}>
              <ObjectTreeNode row={row} active={isActive(row)} onToggle={toggle} />
            </div>
          )
        })}
      </div>
    </div>
  )
}
