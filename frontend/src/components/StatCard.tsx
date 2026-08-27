import { Link } from 'react-router'
import { cn } from '@/lib/utils'

interface StatCardProps {
  label: React.ReactNode
  value: React.ReactNode
  hint?: React.ReactNode
  icon?: React.ReactNode
  to?: string
  tone?: 'default' | 'warning' | 'danger' | 'success'
  className?: string
}

export function StatCard({ label, value, hint, icon, to, tone = 'default', className }: StatCardProps) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">
        <span className="truncate">{label}</span>
        {icon && <span className="text-muted-foreground/70 [&_svg]:size-3.5">{icon}</span>}
      </div>
      <div
        className={cn(
          'mt-1 font-mono text-[22px] leading-7 font-medium tnum tracking-tight',
          tone === 'warning' && 'text-warning',
          tone === 'danger' && 'text-destructive',
          tone === 'success' && 'text-success',
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 truncate text-[12px] text-muted-foreground">{hint}</div>}
    </>
  )
  const cls = cn(
    'block min-w-0 rounded-lg border border-border bg-card px-3.5 py-3 transition-colors',
    to && 'hover:border-foreground/25 hover:bg-muted/40',
    className,
  )
  return to ? (
    <Link to={to} className={cls}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  )
}
