import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { modKey } from '@/lib/utils'

const SHORTCUTS: Array<{ keys: string[]; label: string; group: string }> = [
  { keys: [modKey, 'K'], label: 'Search objects & columns', group: 'Global' },
  { keys: [modKey, '↵'], label: 'Open search result in lineage explorer', group: 'Global' },
  { keys: [modKey, 'B'], label: 'Toggle sidebar', group: 'Global' },
  { keys: [modKey, '⇧', 'D'], label: 'Toggle dark mode', group: 'Global' },
  { keys: ['?'], label: 'This help', group: 'Global' },
  { keys: ['F'], label: 'Refocus on selected node', group: 'Lineage explorer' },
  { keys: ['E'], label: 'Expand selected node (both directions)', group: 'Lineage explorer' },
  { keys: ['H'], label: 'Hide selected node', group: 'Lineage explorer' },
  { keys: ['0'], label: 'Fit view', group: 'Lineage explorer' },
  { keys: ['L'], label: 'Re-layout', group: 'Lineage explorer' },
  { keys: ['Esc'], label: 'Clear selection / close panel', group: 'Lineage explorer' },
]

export function ShortcutsHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const groups = [...new Set(SHORTCUTS.map((s) => s.group))]
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Press ? anywhere to toggle this list.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {groups.map((g) => (
            <div key={g}>
              <div className="mb-1.5 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">{g}</div>
              <ul className="divide-y divide-border/70">
                {SHORTCUTS.filter((s) => s.group === g).map((s) => (
                  <li key={s.label} className="flex items-center justify-between gap-4 py-1.5 text-[13px]">
                    <span>{s.label}</span>
                    <KbdGroup>
                      {s.keys.map((k) => (
                        <Kbd key={k}>{k}</Kbd>
                      ))}
                    </KbdGroup>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
