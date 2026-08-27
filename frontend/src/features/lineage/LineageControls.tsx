import { Columns3, Crosshair, ExternalLink, ListFilter, Maximize2, Package, RefreshCw, Search, TableProperties } from 'lucide-react'
import { Link } from 'react-router'
import type { Confidence, EdgeKind, ObjectKind } from '@/api/types'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useCommandPalette } from '@/features/search/palette-context'
import { EDGE_KIND_LABEL, EDGE_KINDS, KIND_LABEL } from '@/lib/constants'
import type { LineageParams } from '@/lib/lineage-params'
import { MAX_DEPTH, MIN_DEPTH } from '@/lib/lineage-params'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'

const FILTER_KINDS: ObjectKind[] = ['table', 'view', 'procedure', 'scalar_function', 'inline_tvf', 'table_function', 'trigger', 'synonym', 'external']

interface Props {
  scanId: number
  params: LineageParams
  setParams: (patch: Partial<LineageParams>) => void
  focusLabel: { id: number; schema: string; name: string; kind: ObjectKind } | null
  focusColumns: Array<{ name: string; upstream_count: number; downstream_count: number }>
  availableSchemas: string[]
  onFit: () => void
  onRelayout: () => void
  minConfidence: Confidence
  setMinConfidence: (c: Confidence) => void
  showLegend: boolean
  setShowLegend: (v: boolean) => void
  filtersOpen: boolean
  setFiltersOpen: (v: boolean) => void
  embedded?: boolean
  layoutPending: boolean
}

function IconButton({ label, onClick, children, active, asChild, ...rest }: { label: string; onClick?: () => void; children: React.ReactNode; active?: boolean; asChild?: boolean } & React.ComponentProps<typeof Button>) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant={active ? 'secondary' : 'ghost'} size="icon-sm" aria-label={label} onClick={onClick} asChild={asChild} {...rest}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

export function LineageControls(p: Props) {
  const { params, setParams } = p
  const palette = useCommandPalette()
  const activeFilters = params.types.length + params.schemas.length + params.edges.length + (params.cascaded ? 0 : 1) + (params.external ? 0 : 1)

  return (
    <div className="flex min-h-10 shrink-0 flex-wrap items-center gap-x-1.5 gap-y-1 border-b border-border bg-background px-2 py-1">
      {/* focus */}
      <div className="flex min-w-0 items-center gap-1.5 pr-1">
        {p.focusLabel ? (
          <>
            <Crosshair className="size-3.5 shrink-0 text-primary" />
            <ObjectTypeIcon kind={p.focusLabel.kind} className="size-3.5" />
            <span className="max-w-48 truncate font-mono text-[12.5px] font-medium" title={`${p.focusLabel.schema}.${p.focusLabel.name}`}>
              <span className="text-muted-foreground">{p.focusLabel.schema}.</span>
              {p.focusLabel.name}
              {params.level === 'column' && params.col && <span className="text-primary">.{params.col}</span>}
            </span>
            {!p.embedded && (
              <IconButton label="Open detail" asChild>
                <Link to={routes.object(p.scanId, { id: p.focusLabel.id, db: params.db, schema: params.schema, kind: params.kind, name: params.name })}>
                  <ExternalLink />
                </Link>
              </IconButton>
            )}
          </>
        ) : (
          <Button size="sm" variant="outline" onClick={() => palette.open()} className="h-7">
            <Search /> Pick an object…
          </Button>
        )}
      </div>

      <div className="hidden h-5 w-px bg-border lg:block" />

      {/* level */}
      <ToggleGroup type="single" value={params.level} onValueChange={(v) => v && setParams({ level: v as LineageParams['level'] })} size="sm" variant="outline" className="h-7">
        <ToggleGroupItem value="object" aria-label="Objects" className="h-7 gap-1 px-2 text-[12px]">
          <Package className="size-3.5" /> Objects
        </ToggleGroupItem>
        <ToggleGroupItem value="column" aria-label="Columns" className="h-7 gap-1 px-2 text-[12px]">
          <Columns3 className="size-3.5" /> Columns
        </ToggleGroupItem>
      </ToggleGroup>

      {params.level === 'column' && p.focusLabel && (
        <Select value={params.col ?? '__all__'} onValueChange={(v) => setParams({ col: v === '__all__' ? null : v })}>
          <SelectTrigger size="sm" className="h-7 w-44 font-mono text-[12px]" aria-label="Column">
            <SelectValue placeholder="All columns" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All columns with lineage</SelectItem>
            {p.focusColumns.map((c) => (
              <SelectItem key={c.name} value={c.name} className="font-mono text-[12px]">
                {c.name} <span className="text-muted-foreground">↑{c.upstream_count} ↓{c.downstream_count}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <div className="hidden h-5 w-px bg-border lg:block" />

      {/* direction */}
      <ToggleGroup type="single" value={params.dir} onValueChange={(v) => v && setParams({ dir: v as LineageParams['dir'] })} size="sm" variant="outline" className="h-7">
        <ToggleGroupItem value="up" aria-label="Upstream only" className="h-7 px-2 text-[12px]">
          ← Up
        </ToggleGroupItem>
        <ToggleGroupItem value="both" aria-label="Both directions" className="h-7 px-2 text-[12px]">
          Both
        </ToggleGroupItem>
        <ToggleGroupItem value="down" aria-label="Downstream only" className="h-7 px-2 text-[12px]">
          Down →
        </ToggleGroupItem>
      </ToggleGroup>

      {/* depth */}
      <Select value={String(params.depth)} onValueChange={(v) => setParams({ depth: Number(v) })}>
        <SelectTrigger size="sm" className="h-7 w-24 text-[12px]" aria-label="Depth">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Array.from({ length: MAX_DEPTH - MIN_DEPTH + 1 }, (_, i) => i + MIN_DEPTH).map((d) => (
            <SelectItem key={d} value={String(d)} className="text-[12px]">
              Depth {d}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {params.level === 'column' && (
        <Select value={p.minConfidence} onValueChange={(v) => p.setMinConfidence(v as Confidence)}>
          <SelectTrigger size="sm" className="h-7 w-36 text-[12px]" aria-label="Minimum confidence">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="unresolved" className="text-[12px]">
              All confidences
            </SelectItem>
            <SelectItem value="inferred" className="text-[12px]">
              Inferred + exact
            </SelectItem>
            <SelectItem value="exact" className="text-[12px]">
              Exact only
            </SelectItem>
          </SelectContent>
        </Select>
      )}

      {/* filters */}
      <Popover open={p.filtersOpen} onOpenChange={p.setFiltersOpen}>
        <PopoverTrigger asChild>
          <Button variant={activeFilters ? 'secondary' : 'ghost'} size="sm" className="h-7 gap-1 text-[12px]">
            <ListFilter className="size-3.5" /> Filters
            {activeFilters > 0 && <span className="rounded-sm bg-primary/15 px-1 font-mono text-[10px] text-primary">{activeFilters}</span>}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[420px] p-3">
          <div className="grid grid-cols-2 gap-4 text-[12.5px]">
            <div>
              <div className="mb-1.5 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Object types</div>
              <ul className="space-y-1">
                {FILTER_KINDS.map((k) => {
                  const checked = params.types.length === 0 || params.types.includes(k)
                  return (
                    <li key={k}>
                      <label className="flex cursor-pointer items-center gap-2">
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(v) => {
                            const base = params.types.length === 0 ? [...FILTER_KINDS] : [...params.types]
                            const next = v ? [...new Set([...base, k])] : base.filter((x) => x !== k)
                            setParams({ types: next.length === FILTER_KINDS.length ? [] : next })
                          }}
                        />
                        <ObjectTypeIcon kind={k} className="size-3.5" />
                        {KIND_LABEL[k]}
                      </label>
                    </li>
                  )
                })}
              </ul>
            </div>
            <div className="space-y-3">
              <div>
                <div className="mb-1.5 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Schemas</div>
                <ul className="max-h-40 space-y-1 overflow-auto">
                  {p.availableSchemas.map((s) => {
                    const checked = params.schemas.length === 0 || params.schemas.includes(s)
                    return (
                      <li key={s}>
                        <label className="flex cursor-pointer items-center gap-2 font-mono">
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(v) => {
                              const base = params.schemas.length === 0 ? [...p.availableSchemas] : [...params.schemas]
                              const next = v ? [...new Set([...base, s])] : base.filter((x) => x !== s)
                              setParams({ schemas: next.length === p.availableSchemas.length ? [] : next })
                            }}
                          />
                          {s}
                        </label>
                      </li>
                    )
                  })}
                </ul>
              </div>
              <div className="space-y-1.5">
                <label className="flex items-center justify-between gap-2">
                  <Label className="text-[12.5px]">Include cascaded</Label>
                  <Switch checked={params.cascaded} onCheckedChange={(v) => setParams({ cascaded: v })} />
                </label>
                <label className="flex items-center justify-between gap-2">
                  <Label className="text-[12.5px]">Include external</Label>
                  <Switch checked={params.external} onCheckedChange={(v) => setParams({ external: v })} />
                </label>
              </div>
              {params.level === 'object' && (
                <div>
                  <div className="mb-1.5 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Edge kinds (server)</div>
                  <ul className="space-y-1">
                    {EDGE_KINDS.map((k) => {
                      const checked = params.edges.length === 0 || params.edges.includes(k)
                      return (
                        <li key={k}>
                          <label className="flex cursor-pointer items-center gap-2">
                            <Checkbox
                              checked={checked}
                              onCheckedChange={(v) => {
                                const base = params.edges.length === 0 ? [...EDGE_KINDS] : [...params.edges]
                                const next = v ? [...new Set([...base, k])] : base.filter((x) => x !== k)
                                setParams({ edges: next.length === EDGE_KINDS.length ? [] : (next as EdgeKind[]) })
                              }}
                            />
                            {EDGE_KIND_LABEL[k]}
                          </label>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )}
            </div>
          </div>
          {activeFilters > 0 && (
            <div className="mt-3 border-t border-border pt-2">
              <Button size="xs" variant="ghost" onClick={() => setParams({ types: [], schemas: [], edges: [], cascaded: true, external: true })}>
                Reset filters
              </Button>
            </div>
          )}
        </PopoverContent>
      </Popover>

      <div className="ml-auto flex items-center gap-0.5">
        {p.layoutPending && <RefreshCw className="mr-1 size-3.5 animate-spin text-muted-foreground" />}
        <IconButton label="Fit view (0)" onClick={p.onFit}>
          <Maximize2 />
        </IconButton>
        <IconButton label="Re-layout (L)" onClick={p.onRelayout}>
          <RefreshCw />
        </IconButton>
        <IconButton label="Legend" active={p.showLegend} onClick={() => p.setShowLegend(!p.showLegend)}>
          <TableProperties className={cn(!p.showLegend && 'text-muted-foreground')} />
        </IconButton>
      </div>
    </div>
  )
}
