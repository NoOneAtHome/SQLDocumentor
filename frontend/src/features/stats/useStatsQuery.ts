import { keepPreviousData } from '@tanstack/react-query'
import type { SortingState } from '@tanstack/react-table'
import { useMemo, useState } from 'react'
import type { SortOrder } from '@/api/types'

/** Server-sort state shared by the four stats grids; `S` is the endpoint's sort enum. */
export function useServerSort<S extends string>(defaultSort: S, valid: readonly S[], defaultOrder: SortOrder = 'desc') {
  const [sort, setSort] = useState<S>(defaultSort)
  const [order, setOrder] = useState<SortOrder>(defaultOrder)
  const sorting = useMemo<SortingState>(() => [{ id: sort, desc: order === 'desc' }], [sort, order])
  const onSortingChange = (s: SortingState) => {
    const first = s[0]
    const next = valid.find((v) => v === first?.id)
    setSort(next ?? defaultSort)
    setOrder(first ? (first.desc ? 'desc' : 'asc') : defaultOrder)
  }
  return { sort, order, sorting, onSortingChange, query: { sort, order, limit: 200 } }
}

export const STATS_QUERY_OPTS = { staleTime: Infinity, gcTime: 30 * 60 * 1000, placeholderData: keepPreviousData } as const
