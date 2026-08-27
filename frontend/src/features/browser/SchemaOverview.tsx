import { Link } from 'react-router'
import type { DatabaseSummary, SchemaSummary } from '@/api/types'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { KIND_LABEL_PLURAL, OBJECT_KINDS } from '@/lib/constants'
import { formatCompact } from '@/lib/format'
import { routes } from '@/lib/routes'
import { cn } from '@/lib/utils'

function schemaTotal(s: SchemaSummary) {
  return Object.values(s.counts_by_kind).reduce((a, b) => a + (b ?? 0), 0)
}

/** Cards per schema with per-kind counts; selected schemas are highlighted. */
export function SchemaOverview({ scanId, database }: { scanId: number; database: DatabaseSummary }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {database.schemas.map((s) => (
        <Link
          key={s.name}
          to={routes.schema(scanId, database.name, s.name)}
          className={cn('group rounded-lg border border-border bg-card p-3.5 transition-colors hover:border-foreground/25 hover:bg-muted/40', !s.is_selected && 'border-dashed')}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="truncate font-mono text-[13.5px] font-medium">{s.name}</span>
            <span className="shrink-0 font-mono text-[12px] text-muted-foreground tnum">{formatCompact(schemaTotal(s))}</span>
          </div>
          <div className="mt-0.5 text-[11.5px] text-muted-foreground">{s.is_selected ? 'selected in config' : 'cascaded — referenced from selected schemas'}</div>
          <ul className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1">
            {OBJECT_KINDS.filter((k) => (s.counts_by_kind[k] ?? 0) > 0).map((k) => (
              <li key={k} className="flex items-center gap-1 font-mono text-[11.5px] text-muted-foreground tnum">
                <ObjectTypeIcon kind={k} className="size-3" />
                {formatCompact(s.counts_by_kind[k])} <span className="text-muted-foreground/70">{KIND_LABEL_PLURAL[k].toLowerCase()}</span>
              </li>
            ))}
          </ul>
        </Link>
      ))}
    </div>
  )
}
