import { keepPreviousData } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { $api, scanPath } from '@/api/client'

export function useDebounced<T>(value: T, ms = 150): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function useSearch(scanId: number | null, q: string) {
  const debounced = useDebounced(q.trim(), 150)
  return $api.useQuery(
    'get',
    '/api/scans/{scan_id}/search',
    { params: { path: scanPath(scanId ?? 0), query: { q: debounced, kinds: 'object,column', limit: 20 } } },
    { enabled: scanId != null && debounced.length > 0, staleTime: 60_000, placeholderData: keepPreviousData },
  )
}
