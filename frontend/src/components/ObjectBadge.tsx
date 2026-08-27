import { TriangleAlert } from 'lucide-react'
import type { Confidence, LineageStatus, ObjectKind, ObjectScope } from '@/api/types'
import { KIND_COLOR, KIND_LABEL, SCOPE_LABEL } from '@/lib/constants'
import { cn } from '@/lib/utils'
import { ObjectTypeIcon } from './ObjectTypeIcon'

export function KindBadge({ kind, className, iconOnly }: { kind: ObjectKind; className?: string; iconOnly?: boolean }) {
  return (
    <span
      data-kind-color={KIND_COLOR[kind]}
      className={cn(
        'inline-flex h-5 items-center gap-1 rounded-sm border border-(--kind)/25 bg-(--kind)/8 px-1.5 text-[11px] font-medium text-(--kind) whitespace-nowrap',
        className,
      )}
      title={KIND_LABEL[kind]}
    >
      <ObjectTypeIcon kind={kind} className="size-3" />
      {!iconOnly && KIND_LABEL[kind]}
    </span>
  )
}

export function ScopeBadge({ scope, className }: { scope: ObjectScope; className?: string }) {
  if (scope === 'in_scope') return null
  return (
    <span
      className={cn(
        'inline-flex h-5 items-center rounded-sm border px-1.5 text-[11px] font-medium text-muted-foreground whitespace-nowrap',
        scope === 'cascaded' && 'border-dashed border-muted-foreground/50',
        scope === 'external' && 'border-dotted border-muted-foreground/60 text-obj-external',
        className,
      )}
      title={scope === 'cascaded' ? 'Pulled in by a reference from an in-scope object' : 'Outside the scanned databases (name only)'}
    >
      {SCOPE_LABEL[scope]}
    </span>
  )
}

export function ConfidenceBadge({ confidence, className }: { confidence: Confidence; className?: string }) {
  const styles: Record<Confidence, string> = {
    exact: 'border-(--conf-exact)/30 bg-(--conf-exact)/8 text-(--conf-exact)',
    inferred: 'border-(--conf-inferred)/30 bg-(--conf-inferred)/8 text-(--conf-inferred)',
    unresolved: 'border-(--conf-unresolved)/40 bg-(--conf-unresolved)/10 text-(--conf-unresolved)',
  }
  return (
    <span className={cn('inline-flex h-5 items-center rounded-sm border px-1.5 text-[11px] font-medium capitalize', styles[confidence], className)}>
      {confidence}
    </span>
  )
}

export function LineageStatusBadge({ status, hasIssues, className }: { status: LineageStatus; hasIssues?: boolean; className?: string }) {
  if (status === 'n/a') return null
  const styles: Record<Exclude<LineageStatus, 'n/a'>, string> = {
    ok: 'border-success/30 bg-success/8 text-success',
    partial: 'border-warning/40 bg-warning/10 text-warning',
    failed: 'border-destructive/40 bg-destructive/10 text-destructive',
    skipped: 'border-border bg-muted text-muted-foreground',
    pending: 'border-border bg-muted text-muted-foreground',
  }
  return (
    <span className={cn('inline-flex h-5 items-center gap-1 rounded-sm border px-1.5 text-[11px] font-medium', styles[status], className)} title="T-SQL parse status for column lineage">
      {(hasIssues || status === 'partial' || status === 'failed') && <TriangleAlert className="size-3" />}
      lineage {status}
    </span>
  )
}

export function TagChip({ tag, color, className, onRemove }: { tag: string; color?: string | null; className?: string; onRemove?: () => void }) {
  return (
    <span
      className={cn('inline-flex h-5 items-center gap-1 rounded-sm border border-border bg-card px-1.5 text-[11px] font-medium text-foreground/80', className)}
    >
      <span className="size-1.5 rounded-full" style={{ background: color ?? 'var(--muted-foreground)' }} />
      {tag}
      {onRemove && (
        <button type="button" onClick={onRemove} className="ml-0.5 text-muted-foreground hover:text-foreground" aria-label={`Remove tag ${tag}`}>
          ×
        </button>
      )}
    </span>
  )
}
