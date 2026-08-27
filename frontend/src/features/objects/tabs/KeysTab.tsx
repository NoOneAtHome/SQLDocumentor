import { KeyRound, Link2, ShieldCheck } from 'lucide-react'
import type { ForeignKey, ObjectDetail } from '@/api/types'
import { EmptyState } from '@/components/EmptyState'
import { ObjectLink } from '@/components/ObjectLink'
import { cn } from '@/lib/utils'

function Section({ title, icon, count, children }: { title: string; icon: React.ReactNode; count: number; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-card">
      <div className="flex items-center gap-1.5 border-b border-border px-3 py-2 text-[11.5px] font-medium tracking-wide text-muted-foreground uppercase [&_svg]:size-3.5">
        {icon}
        {title}
        <span className="ml-auto font-mono text-[11px] tnum">{count}</span>
      </div>
      {count === 0 ? <div className="px-3 py-3 text-[12.5px] text-muted-foreground">None</div> : children}
    </section>
  )
}

/** One foreign key. `direction` says which side of the relationship the current object is on. */
function FkRow({ fk, direction }: { fk: ForeignKey; direction: 'out' | 'in' }) {
  const other = direction === 'out' ? fk.referenced : fk.parent
  const pairs = fk.columns ?? []
  const ownColumns = pairs.map((p) => (direction === 'out' ? p.column : p.referenced_column))
  const otherColumns = pairs.map((p) => (direction === 'out' ? p.referenced_column : p.column))
  const del = fk.delete_action ?? 'NO_ACTION'
  const upd = fk.update_action ?? 'NO_ACTION'
  return (
    <li className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-3 px-3 py-2 text-[12.5px]">
      <span className="truncate font-mono">{fk.name}</span>
      <span className="font-mono text-[11.5px] text-muted-foreground">({ownColumns.join(', ')})</span>
      <span className="min-w-0 truncate">
        <span className="text-muted-foreground">{direction === 'out' ? '→' : '←'} </span>
        <ObjectLink id={other.id} db={other.db} schema={other.schema} kind={other.kind} name={other.name} />
        <span className="font-mono text-[11.5px] text-muted-foreground"> ({otherColumns.join(', ')})</span>
      </span>
      <span className="flex gap-1 font-mono text-[10.5px] text-muted-foreground">
        {del !== 'NO_ACTION' && <span className="rounded-sm bg-muted px-1">del {del.toLowerCase()}</span>}
        {upd !== 'NO_ACTION' && <span className="rounded-sm bg-muted px-1">upd {upd.toLowerCase()}</span>}
        {fk.is_disabled && <span className="rounded-sm bg-destructive/10 px-1 text-destructive">disabled</span>}
        {fk.is_not_trusted && <span className="rounded-sm bg-warning/10 px-1 text-warning">not trusted</span>}
      </span>
    </li>
  )
}

export function KeysTab({ detail }: { detail: ObjectDetail }) {
  const k = detail.keys
  const unique = k.unique_constraints ?? []
  const fkOut = k.foreign_keys_out ?? []
  const fkIn = k.foreign_keys_in ?? []
  const checks = k.check_constraints ?? []
  const total = (k.primary_key ? 1 : 0) + unique.length + fkOut.length + fkIn.length + checks.length
  if (total === 0) return <div className="p-6"><EmptyState icon={<KeyRound />} title="No keys or constraints" compact /></div>
  return (
    <div className="grid gap-4 p-6 lg:grid-cols-2">
      <Section title="Primary key" icon={<KeyRound />} count={k.primary_key ? 1 : 0}>
        {k.primary_key && (
          <div className="px-3 py-2 font-mono text-[12.5px]">
            {k.primary_key.name ?? 'PRIMARY KEY'} <span className="text-muted-foreground">({(k.primary_key.columns ?? []).join(', ')})</span>
            {k.primary_key.type_desc && <span className="ml-2 text-[10.5px] text-muted-foreground">{k.primary_key.type_desc.toLowerCase()}</span>}
          </div>
        )}
      </Section>
      <Section title="Unique constraints" icon={<ShieldCheck />} count={unique.length}>
        <ul className="divide-y divide-border/60">
          {unique.map((u, i) => (
            <li key={`${u.name ?? 'uq'}-${i}`} className="px-3 py-2 font-mono text-[12.5px]">
              {u.name ?? 'UNIQUE'} <span className="text-muted-foreground">({(u.columns ?? []).join(', ')})</span>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Foreign keys (outgoing)" icon={<Link2 />} count={fkOut.length}>
        <ul className="divide-y divide-border/60">
          {fkOut.map((fk) => (
            <FkRow key={fk.id} fk={fk} direction="out" />
          ))}
        </ul>
      </Section>
      <Section title="Referenced by (incoming)" icon={<Link2 />} count={fkIn.length}>
        <ul className="divide-y divide-border/60">
          {fkIn.map((fk) => (
            <FkRow key={fk.id} fk={fk} direction="in" />
          ))}
        </ul>
      </Section>
      <Section title="Check constraints" icon={<ShieldCheck />} count={checks.length}>
        <ul className="divide-y divide-border/60">
          {checks.map((c) => (
            <li key={c.id} className={cn('grid grid-cols-[minmax(160px,auto)_1fr] gap-3 px-3 py-2 text-[12.5px]', c.is_disabled && 'opacity-60')}>
              <span className="truncate font-mono">
                {c.name}
                {c.column && <span className="text-muted-foreground"> ({c.column})</span>}
              </span>
              <code className="truncate font-mono text-[12px] text-muted-foreground">{c.definition ?? ''}</code>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  )
}
