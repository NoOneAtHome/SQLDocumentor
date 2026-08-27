import type { EdgeKind, ObjectKind } from '@/api/types'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { EDGE_KIND_LABEL, EDGE_KINDS, KIND_COLOR, KIND_LABEL } from '@/lib/constants'
import { cn } from '@/lib/utils'
import { confidenceColor, confidenceDash, edgeKindColor } from './edges/edge-styles'

const LEGEND_KINDS: ObjectKind[] = ['table', 'view', 'procedure', 'scalar_function', 'trigger', 'external']

interface Props {
  level: 'object' | 'column'
  hiddenKinds: ReadonlySet<EdgeKind>
  onToggleKind: (kind: EdgeKind) => void
  className?: string
}

export function LineageLegend({ level, hiddenKinds, onToggleKind, className }: Props) {
  return (
    <div className={cn('w-72 rounded-md border border-border bg-card/95 p-2 text-[10.5px] leading-tight shadow-sm backdrop-blur', className)}>
      <div className="mb-1.5 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Objects</div>
      <ul className="mb-2 grid grid-cols-3 gap-x-2 gap-y-0.5">
        {LEGEND_KINDS.map((k) => (
          <li key={k} data-kind-color={KIND_COLOR[k]} className="flex items-center gap-1.5">
            <span className="h-3 w-1 rounded-sm bg-(--kind)" />
            <ObjectTypeIcon kind={k} className="size-3" />
            <span className="truncate">{KIND_LABEL[k]}</span>
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span className="h-3 w-4 rounded-sm border border-dashed border-muted-foreground" />
          cascaded
        </li>
        <li className="flex items-center gap-1.5">
          <span className="h-3 w-4 rounded-sm border border-dotted border-muted-foreground" />
          external
        </li>
      </ul>
      {level === 'object' ? (
        <>
          <div className="mb-1.5 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Edges · click to toggle</div>
          <ul className="grid grid-cols-2 gap-x-2">
            {EDGE_KINDS.map((k) => (
              <li key={k}>
                <button type="button" onClick={() => onToggleKind(k)} className={cn('flex w-full items-center gap-1.5 rounded-sm px-1 py-px text-left hover:bg-muted', hiddenKinds.has(k) && 'opacity-40 line-through')}>
                  <svg width="18" height="8" className="shrink-0">
                    <line x1="0" y1="4" x2="18" y2="4" stroke={edgeKindColor(k)} strokeWidth="2" />
                  </svg>
                  <span className="truncate">{EDGE_KIND_LABEL[k]}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <div className="mb-1.5 text-[10.5px] font-medium tracking-wide text-muted-foreground uppercase">Confidence</div>
          <ul className="grid grid-cols-3 gap-x-2">
            {(['exact', 'inferred', 'unresolved'] as const).map((c) => (
              <li key={c} className="flex items-center gap-2 px-1">
                <svg width="24" height="8" className="shrink-0">
                  <line x1="0" y1="4" x2="24" y2="4" stroke={confidenceColor(c)} strokeWidth="2" strokeDasharray={confidenceDash(c)} />
                </svg>
                <span className="capitalize">{c}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
