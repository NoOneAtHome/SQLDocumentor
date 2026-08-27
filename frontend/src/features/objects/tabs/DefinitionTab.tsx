import { FileCode, TriangleAlert } from 'lucide-react'
import type { ObjectDetail } from '@/api/types'
import { CodeBlock } from '@/components/CodeBlock'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { formatKb } from '@/lib/format'
import { useObjectDefinition } from '../hooks/useObjectDetail'

export function DefinitionTab({ scanId, detail }: { scanId: number; detail: ObjectDetail }) {
  const q = useObjectDefinition(scanId, detail.summary.id)
  if (q.isPending)
    return (
      <div className="space-y-2 p-6" aria-busy>
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-[420px]" />
      </div>
    )
  if (q.error) return <div className="p-6"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>
  const d = q.data
  if (!d?.definition)
    return (
      <div className="p-6">
        <EmptyState icon={<FileCode />} title="Definition not available" description="The module is encrypted, or the scanning login lacks VIEW DEFINITION on this database." compact />
      </div>
    )
  return (
    <div className="space-y-3 p-6">
      <div className="flex items-center gap-3 text-[12px] text-muted-foreground">
        <span className="font-mono tnum">{formatKb(d.length / 1024)} · {d.definition.split('\n').length} lines</span>
        {d.has_dynamic_sql && (
          <span className="inline-flex items-center gap-1 text-warning">
            <TriangleAlert className="size-3.5" /> contains dynamic SQL — lineage is best-effort
          </span>
        )}
      </div>
      <CodeBlock code={d.definition} maxHeight="calc(100vh - 240px)" />
    </div>
  )
}
