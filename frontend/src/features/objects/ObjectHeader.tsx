import { Waypoints } from 'lucide-react'
import { Link } from 'react-router'
import type { ObjectDetail } from '@/api/types'
import { KindBadge, LineageStatusBadge, ScopeBadge, TagChip } from '@/components/ObjectBadge'
import { ObjectLink } from '@/components/ObjectLink'
import { ObjectTypeIcon } from '@/components/ObjectTypeIcon'
import { CopyButton } from '@/components/CopyButton'
import { Button } from '@/components/ui/button'
import { useTags } from '@/features/annotations/useAnnotation'
import { KIND_COLOR } from '@/lib/constants'
import { formatCompact, formatKb, formatRows } from '@/lib/format'
import { routes } from '@/lib/routes'

export function ObjectHeader({ scanId, detail }: { scanId: number; detail: ObjectDetail }) {
  const s = detail.summary
  const tags = useTags()
  const colorOf = (t: string) => tags.data?.find((x) => x.tag === t)?.color ?? null
  const description = s.annotation_description ?? s.description
  return (
    <header className="border-b border-border px-6 pt-4 pb-0">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span data-kind-color={KIND_COLOR[s.kind]} className="flex size-7 shrink-0 items-center justify-center rounded-md bg-(--kind)/10">
              <ObjectTypeIcon kind={s.kind} className="size-4" />
            </span>
            <h1 className="min-w-0 truncate font-mono text-[17px] leading-7 font-semibold tracking-tight">
              <span className="text-muted-foreground">{s.schema}.</span>
              {s.name}
            </h1>
            <CopyButton value={`[${s.schema}].[${s.name}]`} label="Copy qualified name" />
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <KindBadge kind={s.kind} />
            <ScopeBadge scope={s.scope} />
            <LineageStatusBadge status={s.lineage_status} hasIssues={s.has_lineage_issues} />
            {(s.tags ?? []).map((t) => (
              <TagChip key={t} tag={t} color={colorOf(t)} />
            ))}
            <span className="ml-1 font-mono text-[11.5px] text-muted-foreground">{s.db}</span>
            {detail.parent && (
              <span className="text-[12px] text-muted-foreground">
                on <ObjectLink id={detail.parent.id} db={s.db} schema={detail.parent.schema} kind={detail.parent.kind} name={detail.parent.name} className="text-[12px]" />
              </span>
            )}
            {s.row_count != null && <span className="font-mono text-[11.5px] text-muted-foreground tnum">· {formatRows(s.row_count)}</span>}
            {s.total_size_kb != null && <span className="font-mono text-[11.5px] text-muted-foreground tnum">· {formatKb(s.total_size_kb)}</span>}
            {s.exec_count != null && <span className="font-mono text-[11.5px] text-muted-foreground tnum">· {formatCompact(s.exec_count)} execs</span>}
          </div>
          {description && <p className="mt-2 max-w-3xl text-[13px] text-muted-foreground">{description}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="outline" asChild>
            <Link to={routes.lineage(scanId, s)}>
              <Waypoints /> Open in lineage
            </Link>
          </Button>
        </div>
      </div>
    </header>
  )
}
