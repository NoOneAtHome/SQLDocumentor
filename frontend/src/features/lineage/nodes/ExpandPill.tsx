import { ChevronLeft, ChevronRight, LoaderCircle, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  side: 'left' | 'right'
  count: number
  expanded: boolean
  loading: boolean
  onClick: () => void
  className?: string
}

/** `‹ +3` / `+5 ›` pill on a node edge; flips to `−` once expanded. */
export function ExpandPill({ side, count, expanded, loading, onClick, className }: Props) {
  if (!expanded && count <= 0 && !loading) return null
  const dirLabel = side === 'left' ? 'upstream' : 'downstream'
  const label = loading ? `Loading ${dirLabel}` : expanded ? `− collapse ${dirLabel}` : `+${count} ${dirLabel}`
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        'nodrag nopan absolute top-1/2 z-10 flex h-5 -translate-y-1/2 items-center gap-0.5 rounded-full border bg-card px-1 font-mono text-[10.5px] leading-none font-medium tnum shadow-sm transition-colors',
        side === 'left' ? 'left-0 -translate-x-[calc(100%+6px)] pr-1.5' : 'right-0 translate-x-[calc(100%+6px)] pl-1.5',
        expanded ? 'border-primary/40 text-primary hover:bg-primary/10' : 'border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground',
        className,
      )}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      onDoubleClick={(e) => e.stopPropagation()}
    >
      {side === 'left' && (loading ? <LoaderCircle className="size-3 animate-spin" /> : <ChevronLeft className="size-3" />)}
      {!loading && (expanded ? <Minus className="size-3" /> : <span>+{count}</span>)}
      {side === 'right' && (loading ? <LoaderCircle className="size-3 animate-spin" /> : <ChevronRight className="size-3" />)}
    </button>
  )
}
