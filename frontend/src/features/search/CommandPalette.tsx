import { ChartBar, Database, House, Moon, ScanSearch, Sun, Waypoints } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { PaletteContext, useCommandPalette } from './palette-context'
import { useNavigate } from 'react-router'
import { useScanId } from '@/app/scan-context'
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from '@/components/ui/command'
import { useConnections } from '@/features/connections/useConnections'
import { routes } from '@/lib/routes'
import { useTheme } from '@/lib/theme'
import { modKey } from '@/lib/utils'
import { ColumnResult, ObjectResult } from './SearchResultItem'
import { useSearch } from './useSearch'

const QueryContext = createContext<{ query: string; setQuery: (q: string) => void }>({ query: '', setQuery: () => {} })

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const open = useCallback((initial?: string) => {
    if (initial != null) setQuery(initial)
    setOpen(true)
  }, [])
  const close = useCallback(() => setOpen(false), [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const value = useMemo(() => ({ isOpen, open, close }), [isOpen, open, close])
  const qv = useMemo(() => ({ query, setQuery }), [query])
  return (
    <PaletteContext.Provider value={value}>
      <QueryContext.Provider value={qv}>{children}</QueryContext.Provider>
    </PaletteContext.Provider>
  )
}

/** ⌘K palette: debounced search (Objects / Columns groups) + navigation commands. ⌘↵ opens lineage. */
export function CommandPalette() {
  const { isOpen, close } = useCommandPalette()
  const { query, setQuery } = useContext(QueryContext)
  const scanId = useScanId()
  const connections = useConnections()
  const effectiveScanId = scanId ?? connections.data?.items[0]?.latest_scan?.id ?? null
  const search = useSearch(effectiveScanId, isOpen ? query : '')
  const navigate = useNavigate()
  const { toggle, resolved } = useTheme()
  const [meta, setMeta] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    const down = (e: KeyboardEvent) => setMeta(e.metaKey || e.ctrlKey)
    const up = (e: KeyboardEvent) => setMeta(e.metaKey || e.ctrlKey)
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [isOpen])

  const go = (to: string) => {
    close()
    navigate(to)
  }

  const objects = search.data?.objects ?? []
  const columns = search.data?.columns ?? []
  const hasQuery = query.trim().length > 0
  const connName = connections.data?.items[0]?.name

  return (
    <CommandDialog open={isOpen} onOpenChange={(v) => (v ? undefined : close())} title="Search" description="Search objects and columns, or jump to a page" className="max-w-xl">
      <Command shouldFilter={!hasQuery || effectiveScanId == null} loop>
        <CommandInput placeholder={effectiveScanId != null ? 'Search objects and columns…' : 'Jump to…'} value={query} onValueChange={setQuery} />
        <CommandList className="max-h-[420px]">
          <CommandEmpty>{search.isFetching ? 'Searching…' : 'No results.'}</CommandEmpty>
          {objects.length > 0 && (
            <CommandGroup heading={`Objects · ${meta ? `${modKey}↵ opens lineage` : 'enter opens detail'}`}>
              {objects.map((o) => (
                <CommandItem
                  key={`o-${o.id}`}
                  value={`o-${o.id} ${o.schema}.${o.name}`}
                  onSelect={() => {
                    if (effectiveScanId == null) return
                    go(meta ? routes.lineage(effectiveScanId, o) : routes.object(effectiveScanId, o))
                  }}
                >
                  <ObjectResult object={o} snippet={o.match.snippet ?? undefined} />
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {columns.length > 0 && (
            <CommandGroup heading="Columns">
              {columns.map((c) => (
                <CommandItem
                  key={`c-${c.object.id}-${c.column}`}
                  value={`c-${c.object.id}-${c.column} ${c.object.schema}.${c.object.name}.${c.column}`}
                  onSelect={() => {
                    if (effectiveScanId == null) return
                    go(meta ? routes.lineage(effectiveScanId, { ...c.object, col: c.column, level: 'column' }) : routes.object(effectiveScanId, c.object, 'columns'))
                  }}
                >
                  <ColumnResult object={c.object} column={c.column} dataType={c.data_type ?? ''} />
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {!hasQuery && (
            <CommandGroup heading="Go to">
              <CommandItem onSelect={() => go(routes.home())}>
                <House /> Home
              </CommandItem>
              {connName && (
                <CommandItem onSelect={() => go(routes.connectionScans(connName))}>
                  <ScanSearch /> Scans
                </CommandItem>
              )}
              {effectiveScanId != null && (
                <>
                  <CommandItem onSelect={() => go(routes.scan(effectiveScanId))}>
                    <Database /> Browse snapshot
                  </CommandItem>
                  <CommandItem onSelect={() => go(routes.lineage(effectiveScanId, { db: '', schema: '', kind: '', name: '' }))}>
                    <Waypoints /> Lineage explorer
                  </CommandItem>
                  <CommandItem onSelect={() => go(routes.stats(effectiveScanId, 'tables'))}>
                    <ChartBar /> Stats
                  </CommandItem>
                </>
              )}
              <CommandItem
                onSelect={() => {
                  toggle()
                  close()
                }}
              >
                {resolved === 'dark' ? <Sun /> : <Moon />} Toggle theme
                <CommandShortcut>{modKey}⇧D</CommandShortcut>
              </CommandItem>
            </CommandGroup>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
