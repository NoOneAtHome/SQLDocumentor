import { $api, scanPath } from '@/api/client'
import type { ObjectKind, ObjectSort, ObjectSummary, SortOrder } from '@/api/types'
import { SNAPSHOT_QUERY } from '@/lib/constants'
import { keepPreviousData } from '@tanstack/react-query'

export interface ObjectListFilters {
  db?: string
  schema?: string
  kind?: ObjectKind | ObjectKind[]
  q?: string
  scope?: ObjectSummary['scope']
  sort?: ObjectSort
  order?: SortOrder
  limit?: number
  offset?: number
}

export function useObjectList(scanId: number, filters: ObjectListFilters, opts?: { enabled?: boolean }) {
  const kind = Array.isArray(filters.kind) ? filters.kind.join(',') : filters.kind
  return $api.useQuery(
    'get',
    '/api/scans/{scan_id}/objects',
    {
      params: {
        path: scanPath(scanId),
        query: {
          db: filters.db,
          schema: filters.schema,
          kind,
          q: filters.q || undefined,
          scope: filters.scope,
          sort: filters.sort,
          order: filters.order,
          limit: filters.limit ?? 500,
          offset: filters.offset,
        },
      },
    },
    { ...SNAPSHOT_QUERY, placeholderData: keepPreviousData, enabled: opts?.enabled ?? true },
  )
}
