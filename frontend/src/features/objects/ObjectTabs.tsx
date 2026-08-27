import { useNavigate } from 'react-router'
import type { ObjectDetail } from '@/api/types'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { type ObjectTab, routes } from '@/lib/routes'
import { formatCompact } from '@/lib/format'
import { TAB_LABEL, tabsForKind } from './object-types'

function tabCount(detail: ObjectDetail, tab: ObjectTab): number | null {
  switch (tab) {
    case 'columns':
      return detail.columns?.length ?? 0
    case 'indexes':
      return detail.indexes?.length ?? 0
    case 'keys': {
      const k = detail.keys
      return (k.foreign_keys_out?.length ?? 0) + (k.foreign_keys_in?.length ?? 0) + (k.check_constraints?.length ?? 0) + (k.unique_constraints?.length ?? 0) + (k.primary_key ? 1 : 0)
    }
    case 'parameters':
      return detail.parameters?.length ?? 0
    case 'lineage':
      return detail.lineage_counts.upstream + detail.lineage_counts.downstream
    default:
      return null
  }
}

export function ObjectTabs({ scanId, detail, active }: { scanId: number; detail: ObjectDetail; active: ObjectTab }) {
  const navigate = useNavigate()
  const tabs = tabsForKind(detail.summary.kind)
  return (
    <Tabs value={active} onValueChange={(v) => navigate(routes.object(scanId, detail.summary, v as ObjectTab))} className="gap-0">
      <TabsList variant="line" className="h-9 w-full justify-start gap-0 rounded-none border-b border-border px-4">
        {tabs.map((t) => {
          const n = tabCount(detail, t)
          return (
            <TabsTrigger key={t} value={t} className="h-8 flex-none px-2.5 text-[12.5px] data-active:after:bottom-[-1px]">
              {TAB_LABEL[t]}
              {n != null && n > 0 && <span className="rounded-sm bg-muted px-1 font-mono text-[10.5px] text-muted-foreground tnum">{formatCompact(n)}</span>}
              {t === 'lineage' && (detail.lineage_issues?.length ?? 0) > 0 && <span className="size-1.5 rounded-full bg-warning" title="Lineage issues" />}
            </TabsTrigger>
          )
        })}
      </TabsList>
    </Tabs>
  )
}
