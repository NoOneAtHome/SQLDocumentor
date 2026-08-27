import { Link } from 'react-router'
import type { ObjectKind } from '@/api/types'
import { useScanId } from '@/app/scan-context'
import { type ObjectTab, routes } from '@/lib/routes'
import { cn } from '@/lib/utils'
import { ObjectTypeIcon } from './ObjectTypeIcon'

interface ObjectLinkProps {
  /** Snapshot-local id; needed to link objects that have no db/schema (external). */
  id?: number | null
  db?: string | null
  schema?: string | null
  kind: ObjectKind
  name: string
  tab?: ObjectTab
  /** Show `schema.` prefix (default true). */
  showSchema?: boolean
  showIcon?: boolean
  className?: string
  children?: React.ReactNode
  onClick?: React.MouseEventHandler<HTMLAnchorElement>
}

/** Link to an object detail page in the current scan. Renders plain text outside a scan route. */
export function ObjectLink({ id, db, schema, kind, name, tab, showSchema = true, showIcon = false, className, children, onClick }: ObjectLinkProps) {
  const scanId = useScanId()
  const label = children ?? (
    <>
      {showSchema && schema && <span className="text-muted-foreground">{schema}.</span>}
      {name}
    </>
  )
  const inner = (
    <>
      {showIcon && <ObjectTypeIcon kind={kind} className="size-3.5" />}
      <span className="truncate">{label}</span>
    </>
  )
  if (scanId == null) return <span className={cn('inline-flex items-center gap-1.5 font-mono', className)}>{inner}</span>
  return (
    <Link
      to={routes.object(scanId, { id, db, schema, kind, name }, tab)}
      onClick={onClick}
      className={cn('inline-flex max-w-full items-center gap-1.5 font-mono text-foreground underline-offset-2 hover:text-primary hover:underline', className)}
    >
      {inner}
    </Link>
  )
}
