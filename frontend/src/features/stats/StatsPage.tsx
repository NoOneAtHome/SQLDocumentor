import { useNavigate } from 'react-router'
import { useScanContext } from '@/app/scan-context'
import { PageHeader } from '@/components/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { type StatsPage as StatsPageId, routes } from '@/lib/routes'
import { HotProcsGrid } from './HotProcsGrid'
import { LargestTablesGrid } from './LargestTablesGrid'
import { MissingIndexesGrid } from './MissingIndexesGrid'
import { UnusedIndexesGrid } from './UnusedIndexesGrid'

const PAGES: Array<{ id: StatsPageId; label: string; title: string; description: string }> = [
  { id: 'tables', label: 'Largest tables', title: 'Largest tables', description: 'Row counts and storage from sys.dm_db_partition_stats, per table.' },
  { id: 'indexes', label: 'Unused indexes', title: 'Unused indexes', description: 'Non-clustered indexes with no seeks, scans or lookups since the last restart — but still maintained on every write.' },
  { id: 'procs', label: 'Hot procedures', title: 'Hot procedures & functions', description: 'Execution counts and elapsed time from the plan cache (dm_exec_procedure_stats / function_stats / trigger_stats).' },
  { id: 'missing-indexes', label: 'Missing indexes', title: 'Missing index suggestions', description: 'Optimizer suggestions ranked by improvement measure. Treat as hints, not orders.' },
]

export function StatsPage({ page }: { page: StatsPageId }) {
  const { scanId, summary } = useScanContext()
  const navigate = useNavigate()
  const meta = PAGES.find((p) => p.id === page) ?? PAGES[0]!
  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader eyebrow={`Scan #${scanId} · stats`} title={meta.title} description={meta.description} className="pb-0">
        <Tabs value={meta.id} onValueChange={(v) => navigate(routes.stats(scanId, v as StatsPageId))} className="gap-0">
          <TabsList variant="line" className="-mb-px h-9 w-full justify-start gap-0 p-0">
            {PAGES.map((p) => (
              <TabsTrigger key={p.id} value={p.id} className="h-8 flex-none px-2.5 text-[12.5px]">
                {p.label}
                {p.id === 'indexes' && summary.warnings_summary.unused_indexes > 0 && <span className="rounded-sm bg-warning/10 px-1 font-mono text-[10.5px] text-warning">{summary.warnings_summary.unused_indexes}</span>}
                {p.id === 'missing-indexes' && summary.warnings_summary.missing_index_suggestions > 0 && <span className="rounded-sm bg-muted px-1 font-mono text-[10.5px] text-muted-foreground">{summary.warnings_summary.missing_index_suggestions}</span>}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-auto p-6">
        {meta.id === 'tables' && <LargestTablesGrid scanId={scanId} />}
        {meta.id === 'indexes' && <UnusedIndexesGrid scanId={scanId} />}
        {meta.id === 'procs' && <HotProcsGrid scanId={scanId} />}
        {meta.id === 'missing-indexes' && <MissingIndexesGrid scanId={scanId} />}
      </div>
    </div>
  )
}
