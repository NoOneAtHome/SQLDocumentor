import { Maximize2 } from 'lucide-react'
import { Link } from 'react-router'
import type { ObjectDetail } from '@/api/types'
import { Button } from '@/components/ui/button'
import { LineageExplorer } from '@/features/lineage/LineageExplorer'
import { routes } from '@/lib/routes'

/** Embedded explorer (depth 1, both directions) with a link to the full-page explorer. */
export function LineageTab({ scanId, detail }: { scanId: number; detail: ObjectDetail }) {
  const s = detail.summary
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-1.5">
        <span className="text-[12px] text-muted-foreground">
          {detail.lineage_counts.upstream} upstream · {detail.lineage_counts.downstream} downstream · {detail.lineage_counts.columns_with_lineage} columns with lineage
        </span>
        <Button size="xs" variant="outline" asChild>
          <Link to={routes.lineage(scanId, s)}>
            <Maximize2 /> Open full explorer
          </Link>
        </Button>
      </div>
      <div className="min-h-0 flex-1">
        <LineageExplorer embedded initialFocus={s} />
      </div>
    </div>
  )
}
