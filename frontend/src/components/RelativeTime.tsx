import { useEffect, useState } from 'react'
import { formatDateTime, formatRelative } from '@/lib/format'
import { cn } from '@/lib/utils'

/** "3 min ago" with the absolute timestamp on hover; re-renders every 30 s. */
export function RelativeTime({ value, className }: { value: string | null | undefined; className?: string }) {
  const [, tick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 30_000)
    return () => clearInterval(t)
  }, [])
  if (!value) return <span className={cn('text-muted-foreground', className)}>—</span>
  return (
    <time dateTime={value} title={formatDateTime(value)} className={cn('tnum whitespace-nowrap', className)}>
      {formatRelative(value)}
    </time>
  )
}
