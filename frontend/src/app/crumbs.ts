import type { ComponentType, ReactNode } from 'react'
import { routes } from '@/lib/routes'

export interface Crumb {
  label: string
  to?: string
}

export type RouteParams = Record<string, string | undefined>

export type CrumbsProps = { params: RouteParams; children: (crumbs: Crumb[]) => ReactNode }

/** Route `handle` shape used by the Topbar breadcrumbs. */
export interface RouteHandle {
  /** Crumbs derived from URL params alone. */
  crumbs?: (params: RouteParams) => Crumb[]
  /** Crumbs that need loaded data: a component (so it can use query hooks) that hands them to `children`. */
  Crumbs?: ComponentType<CrumbsProps>
}

/** `db › schema › name`, skipping the levels an external object does not have. */
export function objectCrumbs(scanId: string, ref: { db?: string | null; schema?: string | null; name: string }): Crumb[] {
  const out: Crumb[] = []
  if (ref.db) {
    out.push({ label: ref.db, to: routes.db(scanId, ref.db) })
    if (ref.schema) out.push({ label: ref.schema, to: routes.schema(scanId, ref.db, ref.schema) })
  }
  out.push({ label: ref.name })
  return out
}
