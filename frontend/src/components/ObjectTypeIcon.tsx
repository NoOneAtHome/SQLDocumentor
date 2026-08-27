import {
  Binary,
  Braces,
  Database,
  Eye,
  Globe,
  Hash,
  Link2,
  type LucideProps,
  Package,
  SquareFunction,
  SquareTerminal,
  Table2,
  Zap,
} from 'lucide-react'
import { createElement } from 'react'
import type { ObjectKind } from '@/api/types'
import { KIND_COLOR } from '@/lib/constants'
import { cn } from '@/lib/utils'

const ICONS: Record<ObjectKind, React.ComponentType<LucideProps>> = {
  table: Table2,
  view: Eye,
  procedure: SquareTerminal,
  scalar_function: SquareFunction,
  inline_tvf: SquareFunction,
  table_function: SquareFunction,
  clr_function: Binary,
  trigger: Zap,
  synonym: Link2,
  sequence: Hash,
  table_type: Braces,
  temp_table: Package,
  external: Globe,
}

export function ObjectTypeIcon({
  kind,
  className,
  ...props
}: { kind: ObjectKind } & LucideProps) {
  const iconProps = {
    'data-kind-color': KIND_COLOR[kind],
    'aria-hidden': true,
    className: cn('size-4 shrink-0 text-(--kind)', className),
    ...props,
  } as LucideProps
  return createElement(ICONS[kind] ?? Database, iconProps)
}
