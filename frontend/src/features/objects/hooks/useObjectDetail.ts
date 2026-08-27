import { $api, scanPath } from '@/api/client'
import { SNAPSHOT_QUERY } from '@/lib/constants'

export interface ObjectRefKey {
  /** Snapshot-local object id, when known — lets the by-id detail cache be updated alongside the lookup one. */
  id?: number | null
  db?: string | null
  schema?: string | null
  name: string
}

/** Where a detail page was entered from: by name (`/db/:db/:schema/:kind/:name`) or by id (`/object/:objectId`). */
export type ObjectAddress = { objectId: number } | ObjectRefKey

/** Query init for the name-based lookup; shared with the annotation optimistic update. */
export function lookupInit(scanId: number, ref: ObjectRefKey) {
  return { params: { path: scanPath(scanId), query: { db: ref.db ?? '', schema: ref.schema ?? '', name: ref.name } } }
}

export function lookupQueryKey(scanId: number, ref: ObjectRefKey) {
  return $api.queryOptions('get', '/api/scans/{scan_id}/objects/lookup', lookupInit(scanId, ref)).queryKey
}

/** Query init for the id-based composite detail (`GET /objects/{object_id}`); works for external objects too. */
export function byIdInit(scanId: number, objectId: number) {
  return { params: { path: { scan_id: scanId, object_id: objectId } } }
}

export function byIdQueryKey(scanId: number, objectId: number) {
  return $api.queryOptions('get', '/api/scans/{scan_id}/objects/{object_id}', byIdInit(scanId, objectId)).queryKey
}

/** Every cache entry that may hold this object's composite detail (name lookup + id lookup). */
export function detailQueryKeys(scanId: number, ref: ObjectRefKey) {
  return ref.id != null ? [lookupQueryKey(scanId, ref), byIdQueryKey(scanId, ref.id)] : [lookupQueryKey(scanId, ref)]
}

export function useObjectDetail(scanId: number, ref: ObjectRefKey, opts?: { enabled?: boolean }) {
  return $api.useQuery('get', '/api/scans/{scan_id}/objects/lookup', lookupInit(scanId, ref), { ...SNAPSHOT_QUERY, enabled: opts?.enabled ?? true })
}

export function useObjectById(scanId: number, objectId: number | null) {
  return $api.useQuery('get', '/api/scans/{scan_id}/objects/{object_id}', byIdInit(scanId, objectId ?? 0), { ...SNAPSHOT_QUERY, enabled: objectId != null })
}

/**
 * Composite detail for either address. Both queries are always mounted (hooks must not be
 * conditional); only the one matching the address is enabled, and that one is returned.
 */
export function useObjectDetailByAddress(scanId: number, address: ObjectAddress) {
  const byId = 'objectId' in address
  const named = useObjectDetail(scanId, byId ? { name: '' } : address, { enabled: !byId })
  const ident = useObjectById(scanId, byId ? address.objectId : null)
  return byId ? ident : named
}

export function useObjectDefinition(scanId: number, objectId: number | null, enabled = true) {
  return $api.useQuery('get', '/api/scans/{scan_id}/objects/{object_id}/definition', { params: { path: { scan_id: scanId, object_id: objectId ?? 0 } } }, { ...SNAPSHOT_QUERY, enabled: enabled && objectId != null })
}
