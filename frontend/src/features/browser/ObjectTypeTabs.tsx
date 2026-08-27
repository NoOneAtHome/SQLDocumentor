import { Link } from 'react-router'
import type { ObjectKind } from '@/api/types'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { KIND_LABEL_PLURAL, OBJECT_KINDS } from '@/lib/constants'
import { formatCompact } from '@/lib/format'
import { cn } from '@/lib/utils'

interface Props {
  counts: Partial<Record<ObjectKind, number>>
  active: ObjectKind | null
  hrefFor: (kind: ObjectKind | null) => string
}

/** Horizontal kind tabs (All · Tables · Views · …) with counts; only kinds present are shown. */
export function ObjectTypeTabs({ counts, active, hrefFor }: Props) {
  const total = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0)
  const kinds = OBJECT_KINDS.filter((k) => (counts[k] ?? 0) > 0)
  const tab = (kind: ObjectKind | null, label: string, n: number) => {
    const isActive = active === kind
    return (
      <Link
        key={kind ?? 'all'}
        to={hrefFor(kind)}
        role="tab"
        aria-selected={isActive}
        className={cn(
          'relative flex h-8 shrink-0 items-center gap-1.5 px-2.5 text-[12.5px] font-medium whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground',
          isActive && 'text-foreground after:absolute after:inset-x-1.5 after:-bottom-px after:h-0.5 after:rounded-full after:bg-foreground',
        )}
      >
        {kind && <ObjectTypeIcon kind={kind} className="size-3.5" />}
        {label}
        <span className="rounded-sm bg-muted px-1 font-mono text-[10.5px] text-muted-foreground tnum">{formatCompact(n)}</span>
      </Link>
    )
  }
  return (
    <div role="tablist" className="no-scrollbar flex items-center gap-1 overflow-x-auto border-b border-border">
      {tab(null, 'All', total)}
      {kinds.map((k) => tab(k, KIND_LABEL_PLURAL[k], counts[k] ?? 0))}
    </div>
  )
}
