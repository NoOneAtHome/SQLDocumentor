import { Play } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { routes } from '@/lib/routes'
import { errorMessage } from '@/lib/utils'
import { useStartScan } from './useScanProgress'

export function StartScanDialog({ connection, disabled, navigateOnStart = true }: { connection: string; disabled?: boolean; navigateOnStart?: boolean }) {
  const [open, setOpen] = useState(false)
  const [collectStats, setCollectStats] = useState(true)
  const [parseLineage, setParseLineage] = useState(true)
  const start = useStartScan()
  const navigate = useNavigate()

  const submit = () => {
    start.mutate(
      { params: { path: { name: connection } }, body: { collect_stats: collectStats, parse_lineage: parseLineage } },
      {
        onSuccess: (r) => {
          toast.success(`Scan #${r.scan_id} started`)
          setOpen(false)
          if (navigateOnStart) navigate(routes.connectionScans(connection))
        },
        onError: (e) => toast.error('Could not start scan', { description: errorMessage(e) }),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" disabled={disabled}>
          <Play /> Scan now
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Scan {connection}</DialogTitle>
          <DialogDescription>Creates a new immutable snapshot. The previous snapshot stays browsable.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <label className="flex items-start gap-2.5 text-[13px]">
            <Checkbox checked={collectStats} onCheckedChange={(v) => setCollectStats(v === true)} className="mt-0.5" />
            <span>
              <Label className="cursor-pointer">Collect stats</Label>
              <div className="text-[12px] text-muted-foreground">Row counts, sizes, index usage, proc exec stats, missing indexes (needs VIEW DATABASE STATE).</div>
            </span>
          </label>
          <label className="flex items-start gap-2.5 text-[13px]">
            <Checkbox checked={parseLineage} onCheckedChange={(v) => setParseLineage(v === true)} className="mt-0.5" />
            <span>
              <Label className="cursor-pointer">Parse column lineage</Label>
              <div className="text-[12px] text-muted-foreground">T-SQL bodies of views, functions, procedures and triggers are parsed with sqlglot.</div>
            </span>
          </label>
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={start.isPending}>
            <Play /> Start scan
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
