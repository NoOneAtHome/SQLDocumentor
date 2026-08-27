import { Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { useConnections } from '@/features/connections/useConnections'
import { RunningScanPill } from '@/features/scans/RunningScanPill'
import { ScanSwitcher } from '@/features/scans/ScanSwitcher'
import { useCommandPalette } from '@/features/search/palette-context'
import { modKey } from '@/lib/utils'
import { useOptionalScan, useScanId } from '../scan-context'
import { Breadcrumbs } from './Breadcrumbs'
import { ThemeToggle } from './ThemeToggle'

export function Topbar() {
  const scanId = useScanId()
  const scan = useOptionalScan()
  const { open } = useCommandPalette()
  const connections = useConnections()
  const searchable = scanId != null || connections.data?.items.some((c) => c.latest_scan != null)
  return (
    <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border bg-background/90 px-3 backdrop-blur">
      <SidebarTrigger className="-ml-1" />
      <div className="min-w-0 flex-1">
        <Breadcrumbs />
      </div>
      <RunningScanPill />
      {scanId != null && <ScanSwitcher scanId={scanId} connection={scan?.connection ?? null} />}
      <Button
        variant="outline"
        size="sm"
        className="h-7 w-52 justify-start gap-2 pr-1.5 pl-2 text-muted-foreground"
        onClick={() => open()}
        disabled={!searchable}
        title={searchable ? 'Search objects and columns' : 'Run a scan to enable search'}
      >
        <Search className="size-3.5" />
        <span className="flex-1 truncate text-left text-[12.5px] font-normal">Search…</span>
        <Kbd className="text-[10px]">{modKey}K</Kbd>
      </Button>
      <ThemeToggle />
    </div>
  )
}
