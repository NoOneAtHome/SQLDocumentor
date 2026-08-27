import { Columns3, Eye, GitBranch, Globe, Lightbulb, ListTree, SquareTerminal, Table2, TriangleAlert, Waypoints, Zap } from 'lucide-react'
import { Link } from 'react-router'
import { useScanContext } from '@/app/scan-context'
import { ObjectLink } from '@/components/ObjectLink'
import { PageHeader } from '@/components/PageHeader'
import { RelativeTime } from '@/components/RelativeTime'
import { StatCard } from '@/components/StatCard'
import { SchemaOverview } from '@/features/browser/SchemaOverview'
import { useObjectList } from '@/features/browser/useTreeData'
import { formatCompact, formatDurationMs, formatNumber, formatPercent } from '@/lib/format'
import { routes } from '@/lib/routes'

export default function ScanOverviewPage() {
  const { scanId, scan, summary } = useScanContext()
  const c = summary.counts
  const w = summary.warnings_summary
  const quick = useObjectList(scanId, { kind: ['view', 'procedure', 'table_function', 'inline_tvf'], scope: 'in_scope', sort: 'name', limit: 24 })

  return (
    <div className="h-full overflow-auto">
      <PageHeader
        eyebrow={`${scan.connection} · scan #${scanId}`}
        title="Snapshot overview"
        description={
          <>
            Finished <RelativeTime value={scan.finished_at} /> in {formatDurationMs(scan.duration_ms)} · {c.databases} database{c.databases === 1 ? '' : 's'}, {c.schemas} schemas · lineage coverage {formatPercent(summary.lineage_coverage)}
          </>
        }
        actions={
          <Link to={routes.lineage(scanId, { db: '', schema: '', kind: '', name: '' })} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 text-[13px] font-medium hover:bg-muted">
            <Waypoints className="size-4" /> Lineage explorer
          </Link>
        }
      />
      <div className="space-y-6 p-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
          <StatCard label="Tables" value={formatCompact(c.tables)} icon={<Table2 />} />
          <StatCard label="Views" value={formatCompact(c.views)} icon={<Eye />} />
          <StatCard label="Routines" value={formatCompact(c.procedures + c.functions)} hint={`${c.procedures} procs · ${c.functions} fns`} icon={<SquareTerminal />} />
          <StatCard label="Triggers" value={formatCompact(c.triggers)} icon={<Zap />} />
          <StatCard label="Columns" value={formatCompact(c.columns)} icon={<Columns3 />} />
          <StatCard label="Object edges" value={formatCompact(c.edges_object)} icon={<GitBranch />} />
          <StatCard label="Column edges" value={formatCompact(c.edges_column)} icon={<Waypoints />} />
          <StatCard label="Coverage" value={formatPercent(summary.lineage_coverage)} hint="objects with parsed lineage" tone={(summary.lineage_coverage ?? 0) < 0.8 ? 'warning' : 'success'} />
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Lineage issues" value={formatNumber(w.lineage_issues)} hint="parse / resolution problems" icon={<TriangleAlert />} tone={w.lineage_issues > 0 ? 'warning' : 'default'} to={routes.lineage(scanId, { db: '', schema: '', kind: '', name: '' })} />
          <StatCard label="Unused indexes" value={formatNumber(w.unused_indexes)} hint="maintained but never read" icon={<ListTree />} tone={w.unused_indexes > 0 ? 'warning' : 'default'} to={routes.stats(scanId, 'indexes')} />
          <StatCard label="Missing index suggestions" value={formatNumber(w.missing_index_suggestions)} icon={<Lightbulb />} to={routes.stats(scanId, 'missing-indexes')} />
          <StatCard label="External references" value={formatNumber(w.external_refs)} hint="linked servers / unconfigured DBs" icon={<Globe />} />
        </div>

        {summary.databases.map((db) => (
          <section key={db.name}>
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="font-mono text-[13.5px] font-semibold">
                <Link to={routes.db(scanId, db.name)} className="hover:underline">
                  {db.name}
                </Link>
                {!db.is_configured && <span className="ml-2 text-[11px] font-normal text-muted-foreground">not configured — reached by cascade</span>}
              </h2>
              <span className="text-[12px] text-muted-foreground">{db.schemas.length} schemas</span>
            </div>
            <SchemaOverview scanId={scanId} database={db} />
          </section>
        ))}

        <section>
          <h2 className="mb-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">In-scope views &amp; routines</h2>
          <ul className="grid gap-x-6 gap-y-1 rounded-lg border border-border bg-card p-3 sm:grid-cols-2 xl:grid-cols-3">
            {quick.data?.items.map((o) => (
              <li key={o.id} className="flex items-center gap-2 text-[12.5px]">
                <ObjectLink id={o.id} db={o.db} schema={o.schema} kind={o.kind} name={o.name} showIcon className="min-w-0" />
                {o.has_lineage_issues && <TriangleAlert className="size-3 shrink-0 text-warning" />}
              </li>
            ))}
          </ul>
        </section>

        {(scan.warnings?.length ?? 0) > 0 && (
          <section>
            <h2 className="mb-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Scan warnings</h2>
            <ul className="space-y-1.5">
              {scan.warnings?.map((wn, i) => (
                <li key={i} className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/6 px-3 py-2 text-[12.5px]">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
                  <span>
                    <span className="font-mono text-muted-foreground">
                      {wn.phase}
                      {wn.database ? ` · ${wn.database}` : ''} · {wn.code}
                    </span>{' '}
                    {wn.message}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  )
}
