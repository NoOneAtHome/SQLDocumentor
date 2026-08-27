import { Check, ChevronsUpDown, History } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { formatRelative } from '@/lib/format'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'
import { useScanList } from './useScanProgress'

/** Swaps `:scanId` in the current path so object links survive switching snapshots. */
export function ScanSwitcher({ scanId, connection }: { scanId: number; connection: string | null }) {
  const scans = useScanList(connection)
  const location = useLocation()
  const navigate = useNavigate()
  const succeeded = (scans.data?.items ?? []).filter((s) => s.status === 'succeeded')
  const current = succeeded.find((s) => s.id === scanId)
  const latestId = succeeded[0]?.id

  const go = (id: number) => {
    const path = location.pathname.replace(/^\/s\/[^/]+/, `/s/${id}`)
    navigate(path + location.search)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 gap-1.5 font-mono text-[12px]" aria-label="Switch scan">
          <History className="size-3.5 text-muted-foreground" />
          <span>Scan #{scanId}</span>
          {latestId === scanId && <span className="rounded-sm bg-success/10 px-1 text-[10px] font-medium text-success">latest</span>}
          <ChevronsUpDown className="size-3 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="text-[11.5px] tracking-wide text-muted-foreground uppercase">Snapshots · {connection}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {succeeded.length === 0 && <div className="px-2 py-2 text-[12.5px] text-muted-foreground">No successful scans</div>}
        {succeeded.map((s) => (
          <DropdownMenuItem key={s.id} onSelect={() => go(s.id)} className={cn('font-mono text-[12.5px]', s.id === scanId && 'bg-accent/60')}>
            <span className="w-4">{s.id === scanId && <Check className="size-3.5" />}</span>
            <span className="flex-1">#{s.id}</span>
            <span className="text-muted-foreground">{formatRelative(s.finished_at ?? s.started_at)}</span>
          </DropdownMenuItem>
        ))}
        {connection && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => navigate(routes.connectionScans(connection))}>Scan history &amp; start a scan</DropdownMenuItem>
          </>
        )}
        {!current && succeeded.length > 0 && <div className="px-2 pb-1 text-[11.5px] text-warning">Scan #{scanId} is not in this list.</div>}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
