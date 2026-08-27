import { useQueryClient } from '@tanstack/react-query'
import { SearchX } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import type { ObjectDetail } from '@/api/types'
import { useScanContext } from '@/app/scan-context'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { lookupQueryKey, useObjectDetailByAddress } from '@/features/objects/hooks/useObjectDetail'
import { ObjectHeader } from '@/features/objects/ObjectHeader'
import { ObjectTabs } from '@/features/objects/ObjectTabs'
import { tabsForKind } from '@/features/objects/object-types'
import { ColumnsTab } from '@/features/objects/tabs/ColumnsTab'
import { DefinitionTab } from '@/features/objects/tabs/DefinitionTab'
import { IndexesTab } from '@/features/objects/tabs/IndexesTab'
import { KeysTab } from '@/features/objects/tabs/KeysTab'
import { LineageTab } from '@/features/objects/tabs/LineageTab'
import { NotesTab } from '@/features/objects/tabs/NotesTab'
import { OverviewTab } from '@/features/objects/tabs/OverviewTab'
import { ParametersTab } from '@/features/objects/tabs/ParametersTab'
import { StatsTab } from '@/features/objects/tabs/StatsTab'
import { type ObjectTab, routes } from '@/lib/routes'
import { isNotFound } from '@/lib/utils'

function resolveTab(detail: ObjectDetail | undefined, tabParam: string | undefined): ObjectTab {
  if (!detail) return 'overview'
  const tabs = tabsForKind(detail.summary.kind)
  return tabs.includes(tabParam as ObjectTab) ? (tabParam as ObjectTab) : 'overview'
}

/**
 * Object detail, reachable two ways:
 * - `/s/:scanId/db/:db/:schema/:kind/:name[/:tab]` — by name, stable across scans (canonical).
 * - `/s/:scanId/object/:objectId[/:tab]` — by snapshot-local id, the only address external
 *   objects (no db/schema) have. For fully-named objects this route just resolves the id and
 *   replaces itself with the canonical URL.
 */
export default function ObjectDetailPage() {
  const { scanId, connection } = useScanContext()
  const { objectId: objectIdParam, db = '', schema = '', name = '', tab: tabParam } = useParams()
  const byId = objectIdParam != null
  const objectId = byId ? Number(objectIdParam) : null
  const q = useObjectDetailByAddress(scanId, byId ? { objectId: Number.isFinite(objectId) ? (objectId as number) : 0 } : { db, schema, name })
  const detail = q.data
  const tab = resolveTab(detail, tabParam)

  const qc = useQueryClient()
  const navigate = useNavigate()
  const canonical = byId && detail && detail.summary.db && detail.summary.schema ? routes.object(scanId, detail.summary, tab) : null
  useEffect(() => {
    if (!canonical || !detail) return
    // Seed the name-based cache so the canonical page renders without a second round trip.
    qc.setQueryData(lookupQueryKey(scanId, detail.summary), detail)
    navigate(canonical, { replace: true })
  }, [canonical, detail, navigate, qc, scanId])

  if (q.isPending || canonical) {
    return (
      <div className="space-y-4 p-6" aria-busy>
        <div className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-md" />
          <Skeleton className="h-6 w-72" />
        </div>
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-9 w-full" />
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <Skeleton className="h-60" />
      </div>
    )
  }
  if (q.error) {
    if (isNotFound(q.error)) {
      const browsable = !byId && !!db && !!schema
      return (
        <div className="flex h-full items-center justify-center p-8">
          <EmptyState
            icon={<SearchX />}
            title="Not in this scan"
            description={
              <>
                <span className="font-mono">{byId ? `Object #${objectIdParam}` : `${schema}.${name}`}</span> is not part of snapshot #{scanId}. It may have been created after the scan, dropped, or fall outside the configured schemas — try another snapshot from the scan switcher.
              </>
            }
            action={
              <Button size="sm" variant="outline" asChild>
                {browsable ? <Link to={routes.schema(scanId, db, schema)}>Browse {schema}</Link> : <Link to={routes.scan(scanId)}>Scan overview</Link>}
              </Button>
            }
          />
        </div>
      )
    }
    return (
      <div className="p-6">
        <ErrorState error={q.error} title="Could not load object" onRetry={() => q.refetch()} />
      </div>
    )
  }

  // Re-read through the narrowed query result: `detail` above is typed as possibly undefined.
  const loaded = q.data
  return (
    <div className="flex h-full min-h-0 flex-col">
      <ObjectHeader scanId={scanId} detail={loaded} />
      <ObjectTabs scanId={scanId} detail={loaded} active={tab} />
      <div className={tab === 'lineage' ? 'min-h-0 flex-1' : 'min-h-0 flex-1 overflow-auto'}>
        {tab === 'overview' && <OverviewTab scanId={scanId} detail={loaded} />}
        {tab === 'columns' && <ColumnsTab scanId={scanId} detail={loaded} connection={connection} />}
        {tab === 'indexes' && <IndexesTab detail={loaded} />}
        {tab === 'keys' && <KeysTab detail={loaded} />}
        {tab === 'parameters' && <ParametersTab detail={loaded} />}
        {tab === 'definition' && <DefinitionTab scanId={scanId} detail={loaded} />}
        {tab === 'stats' && <StatsTab detail={loaded} />}
        {tab === 'lineage' && <LineageTab scanId={scanId} detail={loaded} />}
        {tab === 'notes' && <NotesTab scanId={scanId} detail={loaded} connection={connection} />}
      </div>
    </div>
  )
}
