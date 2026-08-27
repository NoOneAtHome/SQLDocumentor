import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

/** Layout-shaped placeholder for a data grid. */
export function GridSkeleton({ rows = 8, columns = 5, className }: { rows?: number; columns?: number; className?: string }) {
  return (
    <div className={cn('overflow-hidden rounded-lg border border-border', className)} aria-busy>
      <div className="flex gap-4 border-b border-border bg-muted/40 px-3 py-2">
        {Array.from({ length: columns }, (_, i) => (
          <Skeleton key={i} className="h-3 flex-1" style={{ maxWidth: i === 0 ? 220 : 120 }} />
        ))}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex gap-4 border-b border-border/60 px-3 py-2.5 last:border-0">
          {Array.from({ length: columns }, (_c, c) => (
            <Skeleton key={c} className="h-3 flex-1" style={{ maxWidth: c === 0 ? 220 : 120, opacity: 1 - r * 0.08 }} />
          ))}
        </div>
      ))}
    </div>
  )
}

export function CardSkeleton({ className, lines = 3 }: { className?: string; lines?: number }) {
  return (
    <div className={cn('rounded-lg border border-border bg-card p-4', className)} aria-busy>
      <Skeleton className="mb-3 h-3 w-24" />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className="mb-2 h-3 last:mb-0" style={{ width: `${90 - i * 18}%` }} />
      ))}
    </div>
  )
}
