import { cn } from '@/lib/utils'

export interface KeyValueItem {
  label: React.ReactNode
  value: React.ReactNode
  mono?: boolean
  /** Span the full row (for long values like DDL). */
  wide?: boolean
}

/** Dense definition list: label column + value column, hairline-separated rows. */
export function KeyValueGrid({ items, className, columns = 1 }: { items: KeyValueItem[]; className?: string; columns?: 1 | 2 | 3 }) {
  return (
    <dl
      className={cn(
        'grid gap-x-6 text-[13px]',
        columns === 1 && 'grid-cols-[minmax(120px,max-content)_1fr]',
        columns === 2 && 'grid-cols-1 md:grid-cols-[repeat(2,minmax(120px,max-content)_1fr)]',
        columns === 3 && 'grid-cols-1 md:grid-cols-[repeat(3,minmax(110px,max-content)_1fr)]',
        className,
      )}
    >
      {items.map((it, i) => (
        <div key={i} className={cn('contents', it.wide && 'col-span-full')}>
          <dt className="border-b border-border/70 py-1.5 pr-3 text-muted-foreground">{it.label}</dt>
          <dd className={cn('min-w-0 border-b border-border/70 py-1.5 text-foreground break-words', it.mono && 'font-mono tnum text-[12.5px]')}>
            {it.value ?? <span className="text-muted-foreground">—</span>}
          </dd>
        </div>
      ))}
    </dl>
  )
}
