import { useQueryClient } from '@tanstack/react-query'
import { $api, scanPath } from '@/api/client'

/** Scan detail; polls every second while the scan is running. */
export function useScanDetail(scanId: number | null, opts?: { poll?: boolean }) {
  return $api.useQuery(
    'get',
    '/api/scans/{scan_id}',
    { params: { path: scanPath(scanId ?? 0) } },
    {
      enabled: scanId != null,
      staleTime: 0,
      refetchInterval: (q) => (opts?.poll !== false && q.state.data?.status === 'running' ? 1_000 : false),
    },
  )
}

export function useScanList(connection: string | null, opts?: { poll?: boolean }) {
  return $api.useQuery(
    'get',
    '/api/connections/{name}/scans',
    { params: { path: { name: connection ?? '' }, query: { limit: 50 } } },
    {
      enabled: !!connection,
      staleTime: 5_000,
      refetchInterval: (q) => (opts?.poll !== false && q.state.data?.items.some((s) => s.status === 'running') ? 1_500 : false),
    },
  )
}

export function useInvalidateScans() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: ['get', '/api/connections'] })
    void qc.invalidateQueries({ queryKey: ['get', '/api/connections/{name}/scans'] })
    void qc.invalidateQueries({ queryKey: ['get', '/api/scans/{scan_id}'] })
  }
}

export function useStartScan() {
  const invalidate = useInvalidateScans()
  return $api.useMutation('post', '/api/connections/{name}/scans', { onSettled: invalidate })
}

export function useCancelScan() {
  const invalidate = useInvalidateScans()
  return $api.useMutation('post', '/api/scans/{scan_id}/cancel', { onSettled: invalidate })
}

export function useDeleteScan() {
  const invalidate = useInvalidateScans()
  return $api.useMutation('delete', '/api/scans/{scan_id}', { onSettled: invalidate })
}
