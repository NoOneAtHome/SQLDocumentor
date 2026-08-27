import { useCallback, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { DEFAULT_LINEAGE_PARAMS, type LineageParams, parseLineageParams, serializeLineageParams } from '@/lib/lineage-params'
import type { ObjectRef } from '@/lib/routes'

export interface LineageParamsApi {
  params: LineageParams
  /** Control changes replace history; pass `push: true` for refocus so Back returns to the old focus. */
  setParams: (patch: Partial<LineageParams>, opts?: { push?: boolean }) => void
}

/** Explorer state lives in the URL (`/s/:scanId/lineage?db&schema&kind&name&col&level&dir&depth&…`). */
export function useLineageParams(): LineageParamsApi {
  const [sp, setSp] = useSearchParams()
  const params = useMemo(() => parseLineageParams(sp), [sp])
  const setParams = useCallback(
    (patch: Partial<LineageParams>, opts?: { push?: boolean }) => {
      setSp((prev) => serializeLineageParams({ ...parseLineageParams(prev), ...patch }), { replace: !opts?.push })
    },
    [setSp],
  )
  return { params, setParams }
}

/** Local (non-URL) params for embedded explorers such as the object Lineage tab. */
export function useLocalLineageParams(initial: ObjectRef, overrides?: Partial<LineageParams>): LineageParamsApi {
  const [params, set] = useState<LineageParams>(() => ({ ...DEFAULT_LINEAGE_PARAMS, db: initial.db ?? '', schema: initial.schema ?? '', kind: initial.kind, name: initial.name, ...overrides }))
  const setParams = useCallback((patch: Partial<LineageParams>) => set((p) => ({ ...p, ...patch })), [])
  return { params, setParams }
}
