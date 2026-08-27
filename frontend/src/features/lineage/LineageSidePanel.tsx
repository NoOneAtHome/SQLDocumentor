import { ArrowDownRight, ArrowUpRight, Crosshair, ExternalLink, EyeOff, MoveLeft, MoveRight, X } from 'lucide-react'
import { Link } from 'react-router'
import type { ColumnLineageEdge, ColumnLineageNode, LineageEdge, LineageNode } from '@/api/types'
import { KindBadge, LineageStatusBadge, ScopeBadge } from '@/components/ObjectBadge'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { Button } from '@/components/ui/button'
import { EDGE_KIND_LABEL } from '@/lib/constants'
import { formatCompact, formatNumber } from '@/lib/format'
import type { LineageParams } from '@/lib/lineage-params'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'
import { ConfidenceBadge } from '@/components/ObjectBadge'
import { type GraphState, isExpanded, visibleEdges } from './graph/graph-state'

type AnyEdge = LineageEdge | ColumnLineageEdge
const isColumnEdge = (e: AnyEdge): e is ColumnLineageEdge => 'confidence' in e
import type { LineageEngine } from './hooks/useLineageGraph'

interface Props {
  scanId: number
  engine: LineageEngine
  params: LineageParams
  selectedId: string | null
  onSelect: (id: string | null) => void
  onRefocus: (nodeId: string) => void
  onClose: () => void
  onSelectColumn: (nodeId: string, column: string) => void
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-[12.5px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right font-mono tnum">{children}</span>
    </div>
  )
}

export function LineageSidePanel({ scanId, engine, params, selectedId, onSelect, onRefocus, onClose, onSelectColumn }: Props) {
  const level = engine.level
  const state: GraphState<LineageNode | ColumnLineageNode, AnyEdge> = level === 'object' ? engine.objectState : engine.columnState
  const entry = selectedId ? state.nodes.get(selectedId) : undefined
  const node = entry?.node as LineageNode | ColumnLineageNode | undefined

  if (!node) {
    const f = engine.focusDetail
    return (
      <div className="flex h-full flex-col">
        <div className="flex h-9 items-center justify-between border-b border-border px-3 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">
          Focus
          <Button variant="ghost" size="icon-xs" onClick={onClose} aria-label="Close panel">
            <X />
          </Button>
        </div>
        <div className="space-y-3 overflow-auto p-3 text-[12.5px]">
          {f ? (
            <>
              <div className="flex items-center gap-2">
                <ObjectTypeIcon kind={f.summary.kind} />
                <span className="min-w-0 truncate font-mono font-medium">
                  {f.summary.schema && <span className="text-muted-foreground">{f.summary.schema}.</span>}
                  {f.summary.name}
                </span>
              </div>
              {(f.summary.annotation_description ?? f.summary.description) && <p className="text-muted-foreground">{f.summary.annotation_description ?? f.summary.description}</p>}
              <div className="divide-y divide-border/60">
                <Row label="Upstream objects">{formatNumber(f.lineage_counts.upstream)}</Row>
                <Row label="Downstream objects">{formatNumber(f.lineage_counts.downstream)}</Row>
                <Row label="Columns with lineage">{formatNumber(f.lineage_counts.columns_with_lineage)}</Row>
                <Row label="Shown">{formatNumber(engine.visibleCount)}</Row>
              </div>
              {(f.lineage_issues?.length ?? 0) > 0 && (
                <div className="rounded-md border border-warning/40 bg-warning/8 p-2 text-[12px]">
                  {f.lineage_issues?.map((i, idx) => (
                    <div key={idx}>
                      <span className="font-mono text-muted-foreground">{i.kind}</span> {i.message}
                    </div>
                  ))}
                </div>
              )}
              <p className="text-[11.5px] text-muted-foreground">Click a node to inspect it · click a pill to expand in place · F refocuses on the selected node · right-click for more.</p>
            </>
          ) : (
            <p className="text-muted-foreground">Pick an object to start.</p>
          )}
        </div>
      </div>
    )
  }

  const edges = visibleEdges(state)
  const incoming = edges.filter((e) => e.target === node.id)
  const outgoing = edges.filter((e) => e.source === node.id)
  const nameOf = (id: string) => {
    const n = state.nodes.get(id)?.node
    return n ? (n.schema ? `${n.schema}.${n.name}` : n.name) : id
  }
  const upExp = isExpanded(state, node.id, 'up')
  const downExp = isExpanded(state, node.id, 'down')
  const objectNode = level === 'object' ? (node as LineageNode) : null
  const columnNode = level === 'column' ? (node as ColumnLineageNode) : null

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-9 items-center justify-between border-b border-border px-3 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">
        Selected
        <Button variant="ghost" size="icon-xs" onClick={onClose} aria-label="Close panel">
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3 text-[12.5px]">
        <div>
          <div className="flex items-center gap-2">
            <ObjectTypeIcon kind={node.kind} />
            <span className="min-w-0 truncate font-mono text-[13px] font-medium" title={`${node.schema ?? ''}.${node.name}`}>
              {node.schema && <span className="text-muted-foreground">{node.schema}.</span>}
              {node.name}
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            <KindBadge kind={node.kind} />
            <ScopeBadge scope={node.scope} />
            {node.has_lineage_issues && <LineageStatusBadge status="partial" hasIssues />}
            <span className="rounded-sm bg-muted px-1.5 font-mono text-[10.5px] text-muted-foreground tnum">hop {node.hop > 0 ? `+${node.hop}` : node.hop}</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-1.5">
          <Button size="sm" variant="secondary" onClick={() => onRefocus(node.id)} disabled={node.id === engine.focusNodeId}>
            <Crosshair /> Focus
          </Button>
          <Button size="sm" variant="outline" asChild>
            <Link to={routes.object(scanId, { id: node.object_id, db: node.db, schema: node.schema, kind: node.kind, name: node.name })}>
              <ExternalLink /> Detail
            </Link>
          </Button>
          <Button size="sm" variant="outline" onClick={() => (upExp ? engine.collapse(node.id, 'up') : void engine.expand(node.id, 'up'))} disabled={!upExp && node.more.upstream === 0}>
            <MoveLeft /> {upExp ? 'Collapse' : `+${node.more.upstream}`} up
          </Button>
          <Button size="sm" variant="outline" onClick={() => (downExp ? engine.collapse(node.id, 'down') : void engine.expand(node.id, 'down'))} disabled={!downExp && node.more.downstream === 0}>
            <MoveRight /> {downExp ? 'Collapse' : `+${node.more.downstream}`} down
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="col-span-2 text-muted-foreground"
            onClick={() => {
              engine.hide(node.id)
              onSelect(null)
            }}
          >
            <EyeOff /> Hide from canvas
          </Button>
        </div>

        {objectNode && (
          <div className="divide-y divide-border/60">
            {objectNode.row_count != null && <Row label="Rows">{formatCompact(objectNode.row_count)}</Row>}
            {objectNode.exec_count != null && <Row label="Executions">{formatCompact(objectNode.exec_count)}</Row>}
            <Row label="Database">{objectNode.db}</Row>
          </div>
        )}

        {columnNode && (
          <section>
            <h3 className="mb-1 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">
              Participating columns · {columnNode.columns?.length ?? 0}/{columnNode.column_count_total}
            </h3>
            <ul className="divide-y divide-border/60 rounded-md border border-border">
              {(columnNode.columns ?? []).map((c) => (
                <li key={c.name}>
                  <button
                    type="button"
                    onClick={() => onSelectColumn(node.id, c.name)}
                    className={cn('flex w-full items-center justify-between gap-2 px-2 py-1 font-mono text-[12px] hover:bg-muted', node.id === engine.focusNodeId && params.col === c.name && 'bg-primary/10 text-primary')}
                  >
                    <span className="truncate">{c.name}</span>
                    <span className="truncate text-[10.5px] text-muted-foreground">{c.data_type}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {[
          { title: 'Incoming', icon: <ArrowUpRight className="size-3" />, list: incoming, other: (e: AnyEdge) => e.source },
          { title: 'Outgoing', icon: <ArrowDownRight className="size-3" />, list: outgoing, other: (e: AnyEdge) => e.target },
        ].map((sec) => (
          <section key={sec.title}>
            <h3 className="mb-1 flex items-center gap-1 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">
              {sec.icon} {sec.title} · {sec.list.length}
            </h3>
            {sec.list.length === 0 ? (
              <div className="text-[12px] text-muted-foreground">None shown</div>
            ) : (
              <ul className="max-h-56 divide-y divide-border/60 overflow-auto rounded-md border border-border">
                {sec.list.map((e) => {
                  const otherId = sec.other(e)
                  return (
                    <li key={e.id}>
                      <button type="button" onClick={() => onSelect(otherId)} className="flex w-full items-center gap-2 px-2 py-1 text-left hover:bg-muted">
                        <span className="min-w-0 flex-1 truncate font-mono text-[12px]">
                          {isColumnEdge(e) ? (
                            <>
                              {nameOf(otherId)}
                              <span className="text-muted-foreground">.{sec.title === 'Incoming' ? e.source_column : e.target_column}</span>
                            </>
                          ) : (
                            nameOf(otherId)
                          )}
                        </span>
                        {isColumnEdge(e) ? (
                          <ConfidenceBadge confidence={e.confidence} className="h-4 text-[9.5px]" />
                        ) : (
                          <span className="shrink-0 rounded-sm bg-muted px-1 font-mono text-[10px] text-muted-foreground" title={EDGE_KIND_LABEL[e.kind]}>
                            {e.kind}
                          </span>
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        ))}
      </div>
    </div>
  )
}
