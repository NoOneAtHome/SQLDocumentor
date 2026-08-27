import { LoaderCircle } from 'lucide-react'
import { Link } from 'react-router'
import { useConnections } from '@/features/connections/useConnections'
import { routes } from '@/lib/routes'
import { useScanDetail } from './useScanProgress'

/** Top-bar pill that appears while any connection has a running scan. */
export function RunningScanPill() {
  const connections = useConnections()
  const running = connections.data?.items.find((c) => c.running_scan_id != null) ?? null
  const scan = useScanDetail(running?.running_scan_id ?? null)
  if (!running) return null
  const p = scan.data?.progress
  return (
    <Link
      to={routes.connectionScans(running.name)}
      className="flex h-7 items-center gap-2 rounded-md border border-info/30 bg-info/8 px-2 font-mono text-[11.5px] text-info hover:bg-info/15"
      title={p?.message}
    >
      <LoaderCircle className="size-3.5 animate-spin" />
      <span>
        scan #{running.running_scan_id}
        {p && (
          <>
            {' '}
            · {p.phase} {p.total > 1 ? `${p.current}/${p.total}` : ''}
          </>
        )}
      </span>
    </Link>
  )
}
