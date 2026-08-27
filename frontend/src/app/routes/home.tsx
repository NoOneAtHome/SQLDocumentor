import { Server, TriangleAlert } from 'lucide-react'
import { $api } from '@/api/client'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { CardSkeleton } from '@/components/GridSkeleton'
import { PageHeader } from '@/components/PageHeader'
import { ConnectionCard } from '@/features/connections/ConnectionCard'
import { ConnectionDialog } from '@/features/connections/ConnectionDialog'
import { useConnections } from '@/features/connections/useConnections'
import { useScanDetail } from '@/features/scans/useScanProgress'

export default function HomePage() {
  const connections = useConnections()
  const health = $api.useQuery('get', '/api/health', undefined, { staleTime: 60_000 })
  const first = connections.data?.items[0]
  const latest = useScanDetail(first?.latest_scan?.id ?? null, { poll: false })

  return (
    <div className="h-full overflow-auto">
      <PageHeader
        eyebrow="SQL Documentor"
        title="Connections"
        description="Each connection is scanned into an immutable snapshot. Browse the latest snapshot, or start a new scan."
        actions={<ConnectionDialog />}
      />
      <div className="space-y-6 p-6">
        {connections.isError && <ErrorState error={connections.error} title="Could not load connections" onRetry={() => connections.refetch()} />}
        {connections.isPending && (
          <div className="grid gap-4 xl:grid-cols-2">
            <CardSkeleton lines={4} />
            <CardSkeleton lines={4} />
          </div>
        )}
        {connections.data && connections.data.items.length === 0 && (
          <EmptyState icon={<Server />} title="No connections configured" description="Add a connection to sqldoc.yaml and restart the server." action={<ConnectionDialog />} />
        )}
        <div className="grid gap-4 xl:grid-cols-2">{connections.data?.items.map((c) => <ConnectionCard key={c.name} connection={c} />)}</div>

        {latest.data && (latest.data.warnings?.length ?? 0) > 0 && (
          <section>
            <h2 className="mb-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Warnings from the latest scan</h2>
            <ul className="space-y-1.5">
              {latest.data.warnings?.map((w, i) => (
                <li key={i} className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/6 px-3 py-2 text-[12.5px]">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
                  <span>
                    <span className="font-mono text-muted-foreground">
                      {w.phase}
                      {w.database ? ` · ${w.database}` : ''} · {w.code}
                    </span>{' '}
                    {w.message}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {health.data && (
          <p className="font-mono text-[11.5px] text-muted-foreground">
            sqldoc {health.data.version} · {health.data.db_path}
          </p>
        )}
      </div>
    </div>
  )
}
