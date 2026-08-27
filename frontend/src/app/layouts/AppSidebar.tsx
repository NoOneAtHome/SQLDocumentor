import { Activity, ChartBar, Database, House, ScanSearch, Settings2, Waypoints } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from '@/components/ui/sidebar'
import { ObjectTree } from '@/features/browser/ObjectTree'
import { useConnections } from '@/features/connections/useConnections'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'
import { useOptionalScan, useScanId } from '../scan-context'

export function AppSidebar() {
  const location = useLocation()
  const scanId = useScanId()
  const scan = useOptionalScan()
  const { state } = useSidebar()
  const connections = useConnections()
  const firstConn = connections.data?.items[0]
  const effectiveScanId = scanId ?? firstConn?.latest_scan?.id ?? null
  const connName = scan?.connection ?? firstConn?.name ?? null

  const nav = [
    { label: 'Home', to: routes.home(), icon: House, active: location.pathname === '/' },
    {
      label: 'Scans',
      to: connName ? routes.connectionScans(connName) : routes.home(),
      icon: ScanSearch,
      active: location.pathname.startsWith('/connections/'),
      disabled: !connName,
    },
    {
      label: 'Browse',
      to: effectiveScanId != null ? routes.scan(effectiveScanId) : routes.home(),
      icon: Database,
      active: /^\/s\/[^/]+(\/db)?(\/|$)/.test(location.pathname) && !location.pathname.includes('/lineage') && !location.pathname.includes('/stats'),
      disabled: effectiveScanId == null,
    },
    {
      label: 'Lineage',
      to: effectiveScanId != null ? routes.lineage(effectiveScanId, { db: '', schema: '', kind: '', name: '' }) : routes.home(),
      icon: Waypoints,
      active: location.pathname.includes('/lineage'),
      disabled: effectiveScanId == null,
    },
    {
      label: 'Stats',
      to: effectiveScanId != null ? routes.stats(effectiveScanId, 'tables') : routes.home(),
      icon: ChartBar,
      active: location.pathname.includes('/stats'),
      disabled: effectiveScanId == null,
    },
  ]

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="h-11 justify-center border-b border-sidebar-border px-2">
        <Link to="/" className="flex items-center gap-2 overflow-hidden px-1">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Activity className="size-3.5" />
          </span>
          <span className={cn('truncate text-[13px] font-semibold tracking-tight', state === 'collapsed' && 'sr-only')}>
            SQL Documentor
          </span>
        </Link>
      </SidebarHeader>
      <SidebarContent className="gap-0">
        <SidebarGroup className="py-1.5">
          <SidebarGroupContent>
            <SidebarMenu>
              {nav.map((item) => (
                <SidebarMenuItem key={item.label}>
                  <SidebarMenuButton asChild isActive={item.active} tooltip={item.label} size="sm" aria-disabled={item.disabled}>
                    <Link to={item.to} className={cn(item.disabled && 'pointer-events-none opacity-50')}>
                      <item.icon />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        {scan && (
          <SidebarGroup className="min-h-0 flex-1 border-t border-sidebar-border p-0 group-data-[collapsible=icon]:hidden">
            <SidebarGroupLabel className="px-3">Objects</SidebarGroupLabel>
            <SidebarGroupContent className="min-h-0 flex-1">
              <ObjectTree />
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>
      <SidebarFooter className="border-t border-sidebar-border">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild isActive={location.pathname === '/settings'} tooltip="Settings" size="sm">
              <Link to={routes.settings()}>
                <Settings2 />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
