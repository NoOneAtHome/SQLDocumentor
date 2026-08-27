import { FileCode, Plus } from 'lucide-react'
import { $api } from '@/api/client'
import { CodeBlock } from '@/components/CodeBlock'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'

const EXAMPLE = `version: 1
storage: { sqlite_path: ./sqldoc.sqlite }
connections:
  - name: local-aw
    host: localhost
    port: 1433
    auth: { mode: sql, username: sa, password: \${MSSQL_SA_PASSWORD} }   # or { mode: integrated }
    encrypt: true
    trust_server_certificate: true
    databases:
      - { name: AdventureWorks2022, schemas: [Sales, HumanResources] }
scan: { cascade_foreign_keys: true, include_triggers_of_cascaded_tables: true, collect_stats: true, parse_lineage: true }`

/** Connections are read-only in the API; this explains where to add one. */
export function ConnectionDialog({ trigger }: { trigger?: React.ReactNode }) {
  const config = $api.useQuery('get', '/api/config')
  return (
    <Dialog>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button size="sm" variant="outline">
            <Plus /> Add connection
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a connection</DialogTitle>
          <DialogDescription>
            Connections are defined in <code className="font-mono">sqldoc.yaml</code> and reloaded on the next{' '}
            <code className="font-mono">sqldoc serve</code>. Secrets come from environment variables or <code className="font-mono">.env</code>; they are never written to SQLite.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-[13px]">
          <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-[12.5px]">
            <FileCode className="size-3.5 text-muted-foreground" />
            <span className="truncate">{config.data?.config_path ?? 'sqldoc.yaml'}</span>
          </div>
          <CodeBlock code={EXAMPLE} plain maxHeight={360} />
        </div>
      </DialogContent>
    </Dialog>
  )
}
