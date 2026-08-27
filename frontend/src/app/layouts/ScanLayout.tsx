import { useMemo } from 'react'
import { Link, Outlet, useParams } from 'react-router'
import { ScanSearch } from 'lucide-react'
import { $api, scanPath } from '@/api/client'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useConnections } from '@/features/connections/useConnections'
import { SNAPSHOT_QUERY } from '@/lib/constants'
import { routes } from '@/lib/routes'
import { isNotFound } from '@/lib/utils'
import { ScanContext, type ScanContextValue } from '../scan-context'

export function ScanLayout() {
  const { scanId: raw } = useParams()
  const scanId = Number(raw)
  const valid = Number.isFinite(scanId)
  const scan = $api.useQuery('get', '/api/scans/{scan_id}', { params: { path: scanPath(scanId) } }, { enabled: valid, staleTime: 10_000 })
  const summary = $api.useQuery('get', '/api/scans/{scan_id}/summary', { params: { path: scanPath(scanId) } }, { enabled: valid && scan.data?.status === 'succeeded', ...SNAPSHOT_QUERY })
  const connections = useConnections()

  const value = useMemo<ScanContextValue | null>(() => {
    if (!scan.data || !summary.data) return null
    return { scanId, scan: scan.data, summary: summary.data, connection: scan.data.connection }
  }, [scan.data, summary.data, scanId])

  if (!valid || isNotFound(scan.error) || isNotFound(summary.error)) {
    const latest = connections.data?.items[0]?.latest_scan?.id
    return (
      <div className="flex h-full items-center justify-center p-8">
        <EmptyState
          icon={<ScanSearch />}
          title="Scan not found"
          description={`There is no snapshot for scan #${raw}. It may have been pruned, or it never finished.`}
          action={
            <div className="flex gap-2">
              {latest != null && (
                <Button size="sm" asChild>
                  <Link to={routes.scan(latest)}>Open latest scan</Link>
                </Button>
              )}
              <Button size="sm" variant="outline" asChild>
                <Link to="/">Home</Link>
              </Button>
            </div>
          }
        />
      </div>
    )
  }

  if (scan.data && scan.data.status !== 'succeeded') {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <EmptyState
          icon={<ScanSearch />}
          title={scan.data.status === 'running' ? 'Scan still running' : `Scan ${scan.data.status}`}
          description={scan.data.status === 'running' ? 'The snapshot becomes browsable once the scan finishes.' : (scan.data.error ?? 'This scan has no browsable snapshot.')}
          action={
            <Button size="sm" asChild>
              <Link to={routes.connectionScans(scan.data.connection)}>View scan progress</Link>
            </Button>
          }
        />
      </div>
    )
  }

  if (scan.error || summary.error) {
    return (
      <div className="p-6">
        <ErrorState error={scan.error ?? summary.error} title="Could not load scan" onRetry={() => (scan.error ? scan.refetch() : summary.refetch())} />
      </div>
    )
  }

  if (!value) {
    return (
      <div className="space-y-4 p-6" aria-busy>
        <Skeleton className="h-5 w-64" />
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    )
  }

  return (
    <ScanContext.Provider value={value}>
      <Outlet />
    </ScanContext.Provider>
  )
}
