import { Waypoints } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { $api, scanPath } from '@/api/client'
import type { Confidence, EdgeKind } from '@/api/types'
import { useScanContext } from '@/app/scan-context'
import { isEditableTarget } from '@/app/layouts/shortcuts'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { ObjectLink } from '@/components/ObjectLink'
import { Button } from '@/components/ui/button'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Skeleton } from '@/components/ui/skeleton'
import { useCommandPalette } from '@/features/search/palette-context'
import { SNAPSHOT_QUERY, isObjectKind } from '@/lib/constants'
import type { LineageParams } from '@/lib/lineage-params'
import { type ObjectRef, routes } from '@/lib/routes'
import { isNotFound } from '@/lib/utils'
import { LineageActionsContext, type LineageActions } from './actions-context'
import { useLineageEngine } from './hooks/useLineageGraph'
import { useLineageParams, useLocalLineageParams } from './hooks/useLineageParams'
import { fitLineageView } from './fit-view'
import { LineageCanvas } from './LineageCanvas'
import { LineageControls } from './LineageControls'
import { LineageSidePanel } from './LineageSidePanel'

interface Props {
  embedded?: boolean
  initialFocus?: ObjectRef
}

function UrlParamsExplorer(props: Props) {
  const api = useLineageParams()
  return <ExplorerBody {...props} {...api} />
}

function LocalParamsExplorer(props: Props & { initialFocus: ObjectRef }) {
  const api = useLocalLineageParams(props.initialFocus, { depth: 1 })
  return <ExplorerBody {...props} {...api} />
}

/** Lineage Explorer: controls bar + ELK/React Flow canvas + side panel. URL-param state unless embedded. */
export function LineageExplorer(props: Props) {
  if (props.embedded && props.initialFocus) return <LocalParamsExplorer {...props} initialFocus={props.initialFocus} />
  return <UrlParamsExplorer {...props} />
}

function ExplorerBody({ embedded, params, setParams }: Props & { params: LineageParams; setParams: (patch: Partial<LineageParams>, opts?: { push?: boolean }) => void }) {
  const { scanId, summary } = useScanContext()
  const navigate = useNavigate()
  const palette = useCommandPalette()
  const engine = useLineageEngine(scanId, params)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [panelOpen, setPanelOpen] = useState(!embedded)
  const [hiddenKinds, setHiddenKinds] = useState<ReadonlySet<EdgeKind>>(() => new Set())
  const [minConfidence, setMinConfidence] = useState<Confidence>('unresolved')
  const [showLegend, setShowLegend] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)

  const focusColumns = $api.useQuery(
    'get',
    '/api/scans/{scan_id}/lineage/objects/{object_id}/columns',
    { params: { path: { scan_id: scanId, object_id: engine.focusDetail?.summary.id ?? 0 } } },
    { ...SNAPSHOT_QUERY, enabled: params.level === 'column' && !!engine.focusDetail },
  )

  const availableSchemas = useMemo(() => [...new Set(summary.databases.flatMap((d) => d.schemas.map((s) => s.name)))].sort(), [summary])
  const state = engine.level === 'object' ? engine.objectState : engine.columnState

  const refocus = useCallback(
    (nodeId: string) => {
      const n = state.nodes.get(nodeId)?.node
      if (!n) return
      setSelectedId(null)
      setParams({ db: n.db ?? '', schema: n.schema ?? '', kind: n.kind, name: n.name, col: null }, { push: true })
    },
    [state, setParams],
  )

  const openDetail = useCallback(
    (nodeId: string) => {
      const n = state.nodes.get(nodeId)?.node
      if (n) navigate(routes.object(scanId, { id: n.object_id, db: n.db, schema: n.schema, kind: n.kind, name: n.name }))
    },
    [state, navigate, scanId],
  )

  const selectColumn = useCallback(
    (nodeId: string, column: string) => {
      const n = state.nodes.get(nodeId)?.node
      if (!n) return
      setParams({ db: n.db ?? '', schema: n.schema ?? '', kind: n.kind, name: n.name, col: column, level: 'column' }, { push: true })
    },
    [state, setParams],
  )

  const actions = useMemo<LineageActions>(
    () => ({
      expand: (id, dir) => void engine.expand(id, dir),
      collapse: engine.collapse,
      toggleShowAll: (id) => void engine.toggleShowAll(id),
      selectColumn,
    }),
    [engine, selectColumn],
  )

  // Explorer shortcuts (only while this explorer is mounted and focus is not in an input).
  useEffect(() => {
    if (embedded) return
    const onKey = (e: KeyboardEvent) => {
      if (isEditableTarget(e) || e.metaKey || e.ctrlKey || e.altKey) return
      switch (e.key) {
        case 'f':
        case 'F':
          if (selectedId) refocus(selectedId)
          break
        case 'e':
        case 'E':
          if (selectedId) {
            void engine.expand(selectedId, 'up')
            void engine.expand(selectedId, 'down')
          }
          break
        case 'h':
        case 'H':
          if (selectedId) {
            engine.hide(selectedId)
            setSelectedId(null)
          }
          break
        case '0':
          fitLineageView()
          break
        case 'l':
        case 'L':
          engine.relayout()
          break
        case 'Escape':
          if (selectedId) setSelectedId(null)
          else setPanelOpen(false)
          break
        default:
          return
      }
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [embedded, selectedId, refocus, engine])

  const onSelect = useCallback((id: string | null) => {
    setSelectedId(id)
    if (id) setPanelOpen(true)
  }, [])

  const toggleKind = useCallback((k: EdgeKind) => {
    setHiddenKinds((s) => {
      const n = new Set(s)
      if (n.has(k)) n.delete(k)
      else n.add(k)
      return n
    })
  }, [])

  const focusLabel = engine.focusDetail ? { id: engine.focusDetail.summary.id, schema: engine.focusDetail.summary.schema ?? '', name: engine.focusDetail.summary.name, kind: engine.focusDetail.summary.kind } : null

  let body: React.ReactNode
  if (engine.status === 'empty') {
    body = <PickObject scanId={scanId} onSearch={() => palette.open()} />
  } else if (engine.status === 'error') {
    body = (
      <div className="p-6">
        {isNotFound(engine.error) ? (
          <EmptyState
            icon={<Waypoints />}
            title="Not in this scan"
            description={`${params.schema}.${params.name} is not part of snapshot #${scanId}. It may have been dropped, renamed, or fall outside the configured schemas — try another scan from the switcher.`}
            action={
              <Button size="sm" variant="outline" onClick={() => palette.open()}>
                Search objects
              </Button>
            }
          />
        ) : (
          <ErrorState error={engine.error} title="Could not load lineage" onRetry={engine.retry} />
        )}
      </div>
    )
  } else if (engine.status === 'resolving' || (engine.status === 'loading' && engine.visibleCount === 0)) {
    body = (
      <div className="relative h-full w-full overflow-hidden p-8" aria-busy>
        <div className="flex items-center gap-24">
          <div className="space-y-6">
            <Skeleton className="h-16 w-60" />
            <Skeleton className="h-16 w-60" />
            <Skeleton className="h-16 w-60" />
          </div>
          <Skeleton className="h-16 w-60 ring-2 ring-primary/30" />
          <div className="space-y-6">
            <Skeleton className="h-16 w-60" />
            <Skeleton className="h-16 w-60" />
          </div>
        </div>
      </div>
    )
  } else {
    body = (
      <LineageCanvas
        engine={engine}
        selectedId={selectedId}
        onSelect={onSelect}
        onRefocus={refocus}
        onOpenDetail={openDetail}
        onDepthDown={() => setParams({ depth: Math.max(1, params.depth - 1) })}
        canDepthDown={params.depth > 1}
        onOpenFilters={() => setFiltersOpen(true)}
        hiddenKinds={hiddenKinds}
        onToggleKind={toggleKind}
        minConfidence={minConfidence}
        showLegend={showLegend}
        showMinimap={!embedded}
        focusColumn={params.col}
        embedded={embedded}
      />
    )
  }

  return (
    <LineageActionsContext.Provider value={actions}>
      <div className="flex h-full min-h-0 flex-col">
        <LineageControls
          scanId={scanId}
          params={params}
          setParams={setParams}
          focusLabel={focusLabel}
          focusColumns={focusColumns.data ?? []}
          availableSchemas={availableSchemas}
          onFit={fitLineageView}
          onRelayout={engine.relayout}
          minConfidence={minConfidence}
          setMinConfidence={setMinConfidence}
          showLegend={showLegend}
          setShowLegend={setShowLegend}
          filtersOpen={filtersOpen}
          setFiltersOpen={setFiltersOpen}
          embedded={embedded}
          layoutPending={engine.layoutPending}
        />
        <ResizablePanelGroup orientation="horizontal" className="min-h-0 flex-1">
          <ResizablePanel defaultSize={panelOpen ? "74" : "100"} minSize="40">
            <div className="h-full min-h-0">{body}</div>
          </ResizablePanel>
          {panelOpen && engine.status !== 'empty' && (
            <>
              <ResizableHandle withHandle />
              <ResizablePanel defaultSize="26" minSize="18" maxSize="45">
                <div className="h-full min-h-0 border-l border-border bg-card">
                  <LineageSidePanel scanId={scanId} engine={engine} params={params} selectedId={selectedId} onSelect={onSelect} onRefocus={refocus} onClose={() => setPanelOpen(false)} onSelectColumn={selectColumn} />
                </div>
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      </div>
    </LineageActionsContext.Provider>
  )
}

function PickObject({ scanId, onSearch }: { scanId: number; onSearch: () => void }) {
  const hubs = $api.useQuery('get', '/api/scans/{scan_id}/lineage/summary', { params: { path: scanPath(scanId) } }, SNAPSHOT_QUERY)
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="w-full max-w-lg space-y-4">
        <EmptyState
          icon={<Waypoints />}
          title="Pick an object to explore"
          description="Search for a table, view, procedure or column — or start from one of the most connected objects in this snapshot."
          action={
            <Button size="sm" onClick={onSearch}>
              Search objects (⌘K)
            </Button>
          }
        />
        {hubs.data && (hubs.data.top_hubs?.length ?? 0) > 0 && (
          <div className="rounded-lg border border-border bg-card">
            <div className="border-b border-border px-3 py-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Lineage hubs</div>
            <ul className="divide-y divide-border/60">
              {hubs.data.top_hubs?.map((h) => (
                <li key={h.object_id} className="flex items-center justify-between gap-3 px-3 py-1.5 text-[12.5px]">
                  {isObjectKind(h.kind) ? (
                    <ObjectLink id={h.object_id} db={h.db} schema={h.schema} kind={h.kind} name={h.name} showIcon />
                  ) : (
                    <span className="font-mono">{h.schema ? `${h.schema}.` : ''}{h.name}</span>
                  )}
                  <span className="font-mono text-[11.5px] text-muted-foreground tnum">↑{h.upstream} ↓{h.downstream} · {h.degree} edges</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
