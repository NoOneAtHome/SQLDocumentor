import { Search } from 'lucide-react'
import { useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router'
import type { ObjectKind, ObjectSort, SortOrder } from '@/api/types'
import { useScanContext } from '@/app/scan-context'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Input } from '@/components/ui/input'
import { ObjectListGrid } from '@/features/browser/ObjectListGrid'
import { ObjectTypeTabs } from '@/features/browser/ObjectTypeTabs'
import { SchemaOverview } from '@/features/browser/SchemaOverview'
import { useObjectList } from '@/features/browser/useTreeData'
import { KIND_LABEL_PLURAL, OBJECT_KIND_SET } from '@/lib/constants'
import { routes } from '@/lib/routes'

const SORTS = new Set<ObjectSort>(['name', 'kind', 'rows', 'size', 'modified'])

export default function SchemaListPage() {
  const { scanId, summary } = useScanContext()
  const { db = '', schema, kind: kindParam } = useParams()
  const [sp, setSp] = useSearchParams()
  const q = sp.get('q') ?? ''
  const sort = (SORTS.has(sp.get('sort') as ObjectSort) ? sp.get('sort') : 'name') as ObjectSort
  const order = (sp.get('order') === 'desc' ? 'desc' : 'asc') as SortOrder
  const kind = kindParam && OBJECT_KIND_SET.has(kindParam) ? (kindParam as ObjectKind) : null

  const database = summary.databases.find((d) => d.name.toLowerCase() === db.toLowerCase())
  const counts = useMemo(() => {
    const out: Partial<Record<ObjectKind, number>> = {}
    for (const s of database?.schemas ?? []) {
      if (schema && s.name.toLowerCase() !== schema.toLowerCase()) continue
      for (const [k, n] of Object.entries(s.counts_by_kind)) out[k as ObjectKind] = (out[k as ObjectKind] ?? 0) + (n ?? 0)
    }
    return out
  }, [database, schema])

  // db-level kind filter lives in ?kind= since that route has no kind segment
  const spKind = sp.get('kind')
  const effectiveKind = kind ?? (!schema && spKind && OBJECT_KIND_SET.has(spKind) ? (spKind as ObjectKind) : null)
  const data = useObjectList(scanId, { db, schema, kind: effectiveKind ?? undefined, q, sort, order, limit: 500 }, { enabled: !!database })
  const update = (patch: Record<string, string | null>) =>
    setSp(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(patch)) {
          if (v) next.set(k, v)
          else next.delete(k)
        }
        return next
      },
      { replace: true },
    )

  if (!database) {
    return (
      <div className="p-8">
        <EmptyState title="Database not in this scan" description={`${db} is not part of snapshot #${scanId}. Switch to another scan or check sqldoc.yaml.`} />
      </div>
    )
  }

  const hrefFor = (k: ObjectKind | null) => {
    const base = schema ? (k ? routes.kindList(scanId, db, schema, k) : routes.schema(scanId, db, schema)) : k ? `${routes.db(scanId, db)}?kind=${k}` : routes.db(scanId, db)
    const qs = new URLSearchParams()
    if (q) qs.set('q', q)
    if (sort !== 'name') qs.set('sort', sort)
    if (order !== 'asc') qs.set('order', order)
    const s = qs.toString()
    return s ? `${base}${base.includes('?') ? '&' : '?'}${s}` : base
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        eyebrow={schema ? database.name : `Scan #${scanId}`}
        title={<span className="font-mono">{schema ?? database.name}</span>}
        description={schema ? (database.schemas.find((s) => s.name === schema)?.is_selected ? 'Selected schema — every object is in scope.' : 'Cascaded schema — objects were pulled in by references from selected schemas.') : `${database.schemas.length} schemas in this snapshot.`}
        className="pb-0"
      >
        {!schema && (
          <div className="pb-4">
            <SchemaOverview scanId={scanId} database={database} />
          </div>
        )}
        <div className="flex items-end justify-between gap-3">
          <ObjectTypeTabs counts={counts} active={effectiveKind} hrefFor={hrefFor} />
          <div className="relative mb-1 shrink-0">
            <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => update({ q: e.target.value || null })} placeholder="Filter by name…" className="h-7 w-56 pl-7 text-[12.5px]" aria-label="Filter objects" />
          </div>
        </div>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-auto p-6">
        {data.error ? (
          <ErrorState error={data.error} onRetry={() => data.refetch()} />
        ) : (
          <ObjectListGrid
            scanId={scanId}
            items={data.data?.items ?? []}
            total={data.data?.total ?? 0}
            loading={data.isPending}
            fetching={data.isFetching && !data.isPending}
            sort={sort}
            order={order}
            onSortChange={(s, o) => update({ sort: s === 'name' ? null : s, order: o === 'asc' ? null : o })}
            showSchema={!schema}
            showKind={!effectiveKind}
            maxHeight="calc(100vh - 300px)"
            emptyState={q ? `No ${effectiveKind ? KIND_LABEL_PLURAL[effectiveKind].toLowerCase() : 'objects'} match “${q}”.` : 'No objects here.'}
          />
        )}
      </div>
    </div>
  )
}
