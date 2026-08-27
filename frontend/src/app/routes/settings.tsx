import { Monitor, Moon, Sun } from 'lucide-react'
import { $api } from '@/api/client'
import { CodeBlock } from '@/components/CodeBlock'
import { ErrorState } from '@/components/ErrorState'
import { KeyValueGrid } from '@/components/KeyValueGrid'
import { PageHeader } from '@/components/PageHeader'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { Skeleton } from '@/components/ui/skeleton'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { ScanOptions } from '@/api/types'
import { type Theme, useTheme } from '@/lib/theme'
import { modKey } from '@/lib/utils'

/** The effective config is an opaque object in the contract; pick the scan options out defensively. */
function scanOptionsOf(config: Record<string, unknown>): Partial<ScanOptions> | null {
  const scan = config.scan
  if (!scan || typeof scan !== 'object') return null
  const out: Partial<ScanOptions> = {}
  for (const key of ['cascade_foreign_keys', 'include_triggers_of_cascaded_tables', 'collect_stats', 'parse_lineage'] as const) {
    const v = (scan as Record<string, unknown>)[key]
    if (typeof v === 'boolean') out[key] = v
  }
  return out
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()
  const config = $api.useQuery('get', '/api/config')
  const health = $api.useQuery('get', '/api/health')
  const scanOptions = config.data ? scanOptionsOf(config.data.config) : null
  return (
    <div className="h-full overflow-auto">
      <PageHeader title="Settings" description="Appearance is stored in this browser. Connections and scan options live in sqldoc.yaml." />
      <div className="max-w-3xl space-y-8 p-6">
        <section className="space-y-2">
          <h2 className="text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Appearance</h2>
          <ToggleGroup type="single" value={theme} onValueChange={(v) => v && setTheme(v as Theme)} variant="outline" size="sm">
            <ToggleGroupItem value="light" className="gap-1.5 px-3">
              <Sun className="size-3.5" /> Light
            </ToggleGroupItem>
            <ToggleGroupItem value="dark" className="gap-1.5 px-3">
              <Moon className="size-3.5" /> Dark
            </ToggleGroupItem>
            <ToggleGroupItem value="system" className="gap-1.5 px-3">
              <Monitor className="size-3.5" /> System
            </ToggleGroupItem>
          </ToggleGroup>
          <p className="text-[12px] text-muted-foreground">
            Shortcut:{' '}
            <KbdGroup>
              <Kbd>{modKey}</Kbd>
              <Kbd>⇧</Kbd>
              <Kbd>D</Kbd>
            </KbdGroup>
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Server</h2>
          {health.isError ? (
            <ErrorState error={health.error} title="API unreachable" onRetry={() => health.refetch()} />
          ) : health.data ? (
            <KeyValueGrid
              items={[
                { label: 'Version', value: health.data.version, mono: true },
                { label: 'SQLite', value: health.data.db_path, mono: true },
                { label: 'Config', value: config.data?.config_path ?? '—', mono: true },
              ]}
            />
          ) : (
            <Skeleton className="h-20" />
          )}
        </section>

        <section className="space-y-2">
          <h2 className="text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase">Effective configuration (secrets stripped)</h2>
          {config.data ? <CodeBlock code={JSON.stringify(config.data.config, null, 2)} plain maxHeight={420} /> : <Skeleton className="h-40" />}
          {scanOptions && (
            <KeyValueGrid
              columns={2}
              items={[
                { label: 'Cascade foreign keys', value: String(scanOptions.cascade_foreign_keys ?? '—') },
                { label: 'Triggers of cascaded tables', value: String(scanOptions.include_triggers_of_cascaded_tables ?? '—') },
                { label: 'Collect stats', value: String(scanOptions.collect_stats ?? '—') },
                { label: 'Parse lineage', value: String(scanOptions.parse_lineage ?? '—') },
              ]}
            />
          )}
        </section>
      </div>
    </div>
  )
}
