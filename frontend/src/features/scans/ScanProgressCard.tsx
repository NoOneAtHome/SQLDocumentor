import { Check, CircleAlert, LoaderCircle, Square, TriangleAlert, X } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import type { ScanDetail } from '@/api/types'
import { RelativeTime } from '@/components/RelativeTime'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { SCAN_PHASES } from '@/lib/constants'
import { formatDurationMs, formatNumber } from '@/lib/format'
import { routes } from '@/lib/routes'
import { cn, errorMessage } from '@/lib/utils'
import { useCancelScan } from './useScanProgress'

export function ScanProgressCard({ scan }: { scan: ScanDetail }) {
  const cancel = useCancelScan()
  const running = scan.status === 'running'
  const p = scan.progress
  const overall = running
    ? Math.min(99, Math.round(((p.phase_index + (p.total ? p.current / p.total : 0)) / p.phase_count) * 100))
    : 100

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          {running ? (
            <LoaderCircle className="size-4 animate-spin text-info" />
          ) : scan.status === 'succeeded' ? (
            <Check className="size-4 text-success" />
          ) : scan.status === 'cancelled' ? (
            <Square className="size-4 text-muted-foreground" />
          ) : (
            <CircleAlert className="size-4 text-destructive" />
          )}
          <span className="text-[14px] font-semibold">Scan #{scan.id}</span>
          <span
            className={cn(
              'rounded-sm px-1.5 py-0.5 text-[11px] font-medium',
              running && 'bg-info/10 text-info',
              scan.status === 'succeeded' && 'bg-success/10 text-success',
              scan.status === 'failed' && 'bg-destructive/10 text-destructive',
              scan.status === 'cancelled' && 'bg-muted text-muted-foreground',
            )}
          >
            {scan.status}
          </span>
          <span className="text-[12px] text-muted-foreground">
            started <RelativeTime value={scan.started_at} />
            {scan.duration_ms != null && <> · {formatDurationMs(scan.duration_ms)}</>}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {running && (
            <Button
              size="xs"
              variant="outline"
              disabled={cancel.isPending}
              onClick={() =>
                cancel.mutate(
                  { params: { path: { scan_id: scan.id } } },
                  { onError: (e) => toast.error('Could not cancel', { description: errorMessage(e) }) },
                )
              }
            >
              <X /> Cancel
            </Button>
          )}
          {scan.status === 'succeeded' && (
            <Button size="xs" asChild>
              <Link to={routes.scan(scan.id)}>Browse latest</Link>
            </Button>
          )}
        </div>
      </div>

      <div className="space-y-3 px-4 py-3">
        <ol className="flex flex-wrap items-center gap-1.5">
          {SCAN_PHASES.map((phase, i) => {
            const done = !running || i < p.phase_index
            const current = running && i === p.phase_index
            return (
              <li
                key={phase}
                className={cn(
                  'flex items-center gap-1 rounded-sm border px-1.5 py-0.5 font-mono text-[11px]',
                  done && scan.status !== 'failed' && 'border-success/30 bg-success/8 text-success',
                  current && 'border-info/40 bg-info/10 text-info',
                  !done && !current && 'border-border text-muted-foreground',
                  scan.status === 'failed' && i >= p.phase_index && 'border-destructive/30 text-destructive',
                )}
              >
                {current ? <LoaderCircle className="size-3 animate-spin" /> : done ? <Check className="size-3" /> : null}
                {phase}
              </li>
            )
          })}
        </ol>
        {running && (
          <>
            <Progress value={overall} className="h-1.5" />
            <div className="flex items-center justify-between font-mono text-[12px] text-muted-foreground tnum">
              <span className="truncate">{p.message}</span>
              <span className="shrink-0">
                {p.phase} {p.current}/{p.total} · {overall}%
              </span>
            </div>
          </>
        )}
        {scan.status === 'failed' && <div className="rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 font-mono text-[12px] text-destructive">{scan.error}</div>}
        {scan.status === 'succeeded' && scan.counts && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-[12px] text-muted-foreground tnum sm:grid-cols-4">
            <span>{formatNumber(scan.counts.tables)} tables</span>
            <span>{formatNumber(scan.counts.views)} views</span>
            <span>{formatNumber(scan.counts.procedures + scan.counts.functions)} routines</span>
            <span>{formatNumber(scan.counts.triggers)} triggers</span>
            <span>{formatNumber(scan.counts.columns)} columns</span>
            <span>{formatNumber(scan.counts.edges_object)} object edges</span>
            <span>{formatNumber(scan.counts.edges_column)} column edges</span>
            <span className={cn(scan.counts.lineage_issues > 0 && 'text-warning')}>{formatNumber(scan.counts.lineage_issues)} lineage issues</span>
          </div>
        )}
        {(scan.warnings?.length ?? 0) > 0 && (
          <ul className="space-y-1">
            {scan.warnings?.map((w, i) => (
              <li key={i} className="flex items-start gap-2 rounded-md bg-warning/8 px-2.5 py-1.5 text-[12px] text-foreground/90">
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
        )}
      </div>
    </div>
  )
}
