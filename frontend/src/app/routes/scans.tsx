import { useParams } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { ScanHistoryTable } from '@/features/scans/ScanHistoryTable'
import { ScanProgressCard } from '@/features/scans/ScanProgressCard'
import { StartScanDialog } from '@/features/scans/StartScanDialog'
import { useScanDetail, useScanList } from '@/features/scans/useScanProgress'
import { Skeleton } from '@/components/ui/skeleton'

export default function ScansPage() {
  const { connId = '' } = useParams()
  const list = useScanList(connId)
  const items = list.data?.items ?? []
  const running = items.find((s) => s.status === 'running') ?? null
  const featured = running ?? items[0] ?? null
  const detail = useScanDetail(featured?.id ?? null)

  return (
    <div className="h-full overflow-auto">
      <PageHeader
        eyebrow={connId}
        title="Scans"
        description="A scan reads the catalog and DMVs, cascades references across schemas and databases, then parses T-SQL for column lineage. Every scan is an immutable snapshot."
        actions={<StartScanDialog connection={connId} disabled={!!running} navigateOnStart={false} />}
      />
      <div className="space-y-6 p-6">
        {list.error && <ErrorState error={list.error} title="Could not load scans" onRetry={() => list.refetch()} />}
        {featured && !detail.data && <Skeleton className="h-40" />}
        {detail.data && <ScanProgressCard scan={detail.data} />}
        <section>
          <h2 className="mb-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">History</h2>
          <ScanHistoryTable scans={items} loading={list.isPending} activeId={featured?.id ?? null} />
        </section>
      </div>
    </div>
  )
}
