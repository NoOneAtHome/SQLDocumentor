import { ArrowDownRight, ArrowUpRight, Globe, TriangleAlert, Zap } from 'lucide-react'
import { Link } from 'react-router'
import type { DepRef, ExecStats, ObjectDetail, TableStats } from '@/api/types'
import { KeyValueGrid } from '@/components/KeyValueGrid'
import { ObjectLink } from '@/components/ObjectLink'
import { StatCard } from '@/components/StatCard'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { MiniLineage } from '@/features/lineage/MiniLineage'
import { KIND_LABEL, edgeKindLabel, isObjectKind } from '@/lib/constants'
import { formatCompact, formatDateTime, formatKb, formatMs, formatNumber, formatRows } from '@/lib/format'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'

function isTableStats(s: ObjectDetail['stats']): s is TableStats {
  return s?.kind === 'table'
}
function isExecStats(s: ObjectDetail['stats']): s is ExecStats {
  return s?.kind === 'exec'
}

function DepList({ title, icon, deps, db }: { title: string; icon: React.ReactNode; deps: DepRef[]; db: string | null | undefined }) {
  return (
    <div className="min-w-0 rounded-lg border border-border bg-card">
      <div className="flex items-center gap-1.5 border-b border-border px-3 py-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase [&_svg]:size-3.5">
        {icon}
        {title}
        <span className="ml-auto font-mono text-[11px] tnum">{deps.length}</span>
      </div>
      {deps.length === 0 ? (
        <div className="px-3 py-3 text-[12.5px] text-muted-foreground">None</div>
      ) : (
        <ul className="max-h-64 divide-y divide-border/60 overflow-auto">
          {deps.map((d, i) => (
            <li key={`${d.object_id ?? d.name}-${i}`} className="flex items-center gap-2 px-3 py-1.5 text-[12.5px]">
              {isObjectKind(d.kind) && d.object_id != null ? (
                <ObjectLink id={d.object_id} db={d.db || db} schema={d.schema} kind={d.kind} name={d.name} showIcon className={cn('min-w-0 flex-1', d.scope === 'cascaded' && 'text-foreground/80')} />
              ) : (
                <span className="min-w-0 flex-1 truncate font-mono text-muted-foreground" title="Unresolved reference">
                  {d.referenced_name ?? d.name}
                </span>
              )}
              <span className="shrink-0 rounded-sm bg-muted px-1 font-mono text-[10.5px] text-muted-foreground" title={edgeKindLabel(d.edge_kind)}>
                {d.edge_kind}
              </span>
              {d.resolution !== 'resolved' && <span className="shrink-0 text-[10.5px] text-warning">{d.resolution}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function OverviewTab({ scanId, detail }: { scanId: number; detail: ObjectDetail }) {
  const s = detail.summary
  const stats = detail.stats
  const issues = detail.lineage_issues ?? []
  const triggers = detail.triggers ?? []
  const items = [
    { label: 'Kind', value: KIND_LABEL[s.kind] },
    { label: 'Database', value: s.db, mono: true },
    { label: 'Object id', value: detail.sql_object_id ?? '—', mono: true },
    { label: 'Created', value: formatDateTime(detail.created_at) },
    { label: 'Modified', value: formatDateTime(detail.modified_at) },
    { label: 'Object key', value: s.object_key, mono: true },
    ...(detail.ms_description ? [{ label: 'MS_Description', value: detail.ms_description }] : []),
  ]

  return (
    <div className="space-y-5 p-6">
      {s.kind === 'external' && (
        <Alert>
          <Globe />
          <AlertTitle>External object</AlertTitle>
          <AlertDescription>
            Referenced from a linked server or a database that is not configured on this connection
            {detail.external_server && (
              <>
                {' '}
                — <span className="font-mono">{[detail.external_server, s.db, s.schema, s.name].filter(Boolean).join('.')}</span>
              </>
            )}
            . Only the name is known; add its database to <span className="font-mono">sqldoc.yaml</span> to document it.
          </AlertDescription>
        </Alert>
      )}
      {s.kind === 'trigger' && (
        <Alert>
          <Zap />
          <AlertTitle>
            {detail.is_instead_of_trigger ? 'INSTEAD OF' : 'AFTER'} {detail.trigger_events ?? ''} trigger
            {detail.is_disabled && <span className="ml-2 text-destructive">disabled</span>}
          </AlertTitle>
          <AlertDescription>
            Fires on{' '}
            {detail.parent ? <ObjectLink id={detail.parent.id} db={s.db} schema={detail.parent.schema} kind={detail.parent.kind} name={detail.parent.name} /> : 'its parent table'}.
          </AlertDescription>
        </Alert>
      )}
      {issues.length > 0 && (
        <Alert className="border-warning/40 bg-warning/8">
          <TriangleAlert className="text-warning" />
          <AlertTitle>
            {issues.length} lineage {issues.length === 1 ? 'issue' : 'issues'}
          </AlertTitle>
          <AlertDescription>
            <ul className="mt-1 space-y-1">
              {issues.map((i, idx) => (
                <li key={idx} className="text-[12.5px]">
                  <span className="font-mono text-muted-foreground">
                    {i.kind}
                    {i.statement_index != null ? ` #${i.statement_index}` : ''}
                  </span>{' '}
                  {i.message}
                  {i.snippet && <pre className="mt-0.5 truncate rounded-sm bg-muted px-1.5 py-0.5 font-mono text-[11.5px] text-muted-foreground">{i.snippet}</pre>}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {isTableStats(stats) && (
          <>
            <StatCard label="Rows" value={formatCompact(stats.row_count)} hint={formatRows(stats.row_count)} to={routes.object(scanId, s, 'stats')} />
            <StatCard label="Data + index" value={formatKb((stats.data_kb ?? 0) + (stats.index_kb ?? 0))} hint={`${formatKb(stats.data_kb)} data · ${formatKb(stats.index_kb)} index`} to={routes.object(scanId, s, 'stats')} />
          </>
        )}
        {isExecStats(stats) && (
          <>
            <StatCard label="Executions" value={formatCompact(stats.exec_count)} hint={`since ${formatDateTime(stats.since_server_start)}`} to={routes.object(scanId, s, 'stats')} />
            <StatCard label="Avg elapsed" value={formatMs(stats.avg_ms)} hint={`max ${formatMs(stats.max_ms)}`} to={routes.object(scanId, s, 'stats')} />
          </>
        )}
        <StatCard label="Upstream" value={formatNumber(detail.lineage_counts.upstream)} hint="objects feeding this" icon={<ArrowUpRight />} to={routes.lineage(scanId, { ...s, dir: 'up' })} />
        <StatCard label="Downstream" value={formatNumber(detail.lineage_counts.downstream)} hint={`${detail.lineage_counts.columns_with_lineage} columns with lineage`} icon={<ArrowDownRight />} to={routes.lineage(scanId, { ...s, dir: 'down' })} />
      </div>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Lineage · 1 hop</h2>
          <Link to={routes.lineage(scanId, s)} className="text-[12px] text-primary underline-offset-2 hover:underline">
            Open full explorer →
          </Link>
        </div>
        <MiniLineage scanId={scanId} objectId={s.id} focusRef={s} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <DepList title="Uses" icon={<ArrowUpRight />} deps={detail.dependencies.uses ?? []} db={s.db} />
        <DepList title="Used by" icon={<ArrowDownRight />} deps={detail.dependencies.used_by ?? []} db={s.db} />
      </div>

      {triggers.length > 0 && (
        <section>
          <h2 className="mb-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Triggers</h2>
          <ul className="divide-y divide-border/60 rounded-lg border border-border bg-card">
            {triggers.map((t) => (
              <li key={t.id} className="flex items-center gap-3 px-3 py-2 text-[12.5px]">
                <ObjectLink id={t.id} db={s.db} schema={s.schema} kind="trigger" name={t.name} showIcon showSchema={false} />
                <span className="font-mono text-[11.5px] text-muted-foreground">
                  {t.is_instead_of ? 'INSTEAD OF' : 'AFTER'} {t.events ?? ''}
                </span>
                {t.is_disabled && <span className="text-[11px] text-destructive">disabled</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Properties</h2>
        <KeyValueGrid items={items} columns={2} />
      </section>
    </div>
  )
}
