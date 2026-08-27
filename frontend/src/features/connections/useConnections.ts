import { $api } from '@/api/client'

export function useConnections(opts?: { poll?: boolean }) {
  return $api.useQuery('get', '/api/connections', undefined, {
    staleTime: 10_000,
    refetchInterval: (q) => (opts?.poll || q.state.data?.items.some((c) => c.running_scan_id != null) ? 2_000 : false),
  })
}

export function useConnection(name: string | null) {
  const q = useConnections()
  return { ...q, connection: name ? (q.data?.items.find((c) => c.name === name) ?? null) : null }
}
