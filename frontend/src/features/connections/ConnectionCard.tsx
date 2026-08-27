import { Database, KeyRound, Server, ShieldCheck, Unplug } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { $api } from '@/api/client'
import type { ConnectionInfo } from '@/api/types'
import { RelativeTime } from '@/components/RelativeTime'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { StartScanDialog } from '@/features/scans/StartScanDialog'
import { formatDurationMs, formatNumber } from '@/lib/format'
import { routes } from '@/lib/routes'
import { cn, errorMessage } from '@/lib/utils'

function ScanStatus({ status }: { status: string }) {
  const tone: Record<string, string> = {
    succeeded: 'text-success',
    failed: 'text-destructive',
    running: 'text-info',
    cancelled: 'text-muted-foreground',
  }
  return <span className={cn('font-medium', tone[status])}>{status}</span>
}

export function ConnectionCard({ connection }: { connection: ConnectionInfo }) {
  const latest = connection.latest_scan
  const test = $api.useMutation('post', '/api/connections/{name}/test')
  const [tested, setTested] = useState<string | null>(null)

  const runTest = () => {
    test.mutate(
      { params: { path: { name: connection.name } } },
      {
        onSuccess: (r) => {
          if (r.ok) {
            setTested(`${r.server_name} · ${r.edition} · ${r.auth_scheme} · ${r.driver}`)
            toast.success(`Connected to ${r.server_name}`, { description: `${r.version} — auth ${r.auth_scheme}` })
          } else {
            setTested(null)
            toast.error('Connection test failed', { description: r.error })
          }
        },
        onError: (e) => toast.error('Connection test failed', { description: errorMessage(e) }),
      },
    )
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
              <Server className="size-3.5" />
            </span>
            <h2 className="truncate text-[15px] font-semibold tracking-tight">{connection.name}</h2>
            {connection.running_scan_id != null && (
              <Badge variant="secondary" className="gap-1 text-info">
                <span className="size-1.5 animate-pulse rounded-full bg-info" /> scanning
              </Badge>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[12px] text-muted-foreground">
            <span>
              {connection.host}:{connection.port}
            </span>
            <span className="inline-flex items-center gap-1">
              {connection.auth_mode === 'integrated' ? <ShieldCheck className="size-3" /> : <KeyRound className="size-3" />}
              {connection.auth_mode === 'integrated' ? 'integrated (Kerberos)' : 'SQL login'}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="outline" onClick={runTest} disabled={test.isPending}>
            <Unplug className={cn(test.isPending && 'animate-pulse')} /> Test
          </Button>
          <StartScanDialog connection={connection.name} disabled={connection.running_scan_id != null} />
        </div>
      </div>

      {tested && <div className="rounded-md border border-success/30 bg-success/8 px-3 py-1.5 font-mono text-[12px] text-success">{tested}</div>}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-md border border-border/70 bg-muted/30 p-3">
          <div className="mb-1.5 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Databases</div>
          <ul className="space-y-1.5">
            {connection.databases.map((db) => (
              <li key={db.name} className="flex items-start gap-2 text-[13px]">
                <Database className="mt-0.5 size-3.5 shrink-0 text-obj-table" />
                <div className="min-w-0">
                  <div className="truncate font-mono">{db.name}</div>
                  <div className="flex flex-wrap gap-1">
                    {db.schemas.map((s) => (
                      <span key={s} className="rounded-sm bg-card px-1 font-mono text-[11px] text-muted-foreground ring-1 ring-border">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-md border border-border/70 bg-muted/30 p-3">
          <div className="mb-1.5 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Latest scan</div>
          {latest ? (
            <div className="space-y-1 text-[13px]">
              <div className="flex items-center justify-between">
                <span>
                  #{latest.id} · <ScanStatus status={latest.status} />
                </span>
                <RelativeTime value={latest.finished_at ?? latest.started_at} className="text-muted-foreground" />
              </div>
              {latest.counts && (
                <div className="font-mono text-[12px] text-muted-foreground tnum">
                  {formatNumber(latest.counts.tables)} tables · {formatNumber(latest.counts.views)} views · {formatNumber(latest.counts.procedures + latest.counts.functions)} routines ·{' '}
                  {formatNumber(latest.counts.edges_column)} column edges · {formatDurationMs(latest.duration_ms)}
                </div>
              )}
              <div className="flex gap-2 pt-1">
                <Button size="xs" asChild>
                  <Link to={routes.scan(latest.id)}>Browse latest</Link>
                </Button>
                <Button size="xs" variant="ghost" asChild>
                  <Link to={routes.connectionScans(connection.name)}>Scan history</Link>
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-[13px] text-muted-foreground">
              No successful scan yet.{' '}
              <Link className="text-primary underline-offset-2 hover:underline" to={routes.connectionScans(connection.name)}>
                Run one
              </Link>
              .
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
