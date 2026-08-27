import { useCallback, useState } from 'react'
import { Outlet } from 'react-router'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { CommandPalette, CommandPaletteProvider } from '@/features/search/CommandPalette'
import { ShortcutsHelp } from './ShortcutsHelp'
import { useGlobalShortcuts } from './shortcuts'
import { AppSidebar } from './AppSidebar'
import { Topbar } from './Topbar'

const SIDEBAR_KEY = 'sqldoc.sidebar'

function readSidebar(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) !== 'closed'
  } catch {
    return true
  }
}

function Shell() {
  const [open, setOpen] = useState(readSidebar)
  const onOpenChange = useCallback((v: boolean) => {
    setOpen(v)
    try {
      localStorage.setItem(SIDEBAR_KEY, v ? 'open' : 'closed')
    } catch {
      /* ignore */
    }
  }, [])
  const [helpOpen, setHelpOpen] = useState(false)
  useGlobalShortcuts({ onHelp: () => setHelpOpen((v) => !v) })

  return (
    <SidebarProvider open={open} onOpenChange={onOpenChange} style={{ '--sidebar-width': '17.5rem' } as React.CSSProperties} className="h-svh min-h-0 overflow-hidden">
      <AppSidebar />
      <SidebarInset className="flex h-svh min-h-0 min-w-0 flex-col overflow-hidden">
        <Topbar />
        <div className="relative min-h-0 flex-1 overflow-hidden">
          <Outlet />
        </div>
      </SidebarInset>
      <CommandPalette />
      <ShortcutsHelp open={helpOpen} onOpenChange={setHelpOpen} />
    </SidebarProvider>
  )
}

export function AppLayout() {
  return (
    <CommandPaletteProvider>
      <Shell />
    </CommandPaletteProvider>
  )
}
