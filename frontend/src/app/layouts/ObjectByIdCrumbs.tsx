import { useObjectById } from '@/features/objects/hooks/useObjectDetail'
import { type CrumbsProps, objectCrumbs } from '../crumbs'

/**
 * Breadcrumbs for `/s/:scanId/object/:objectId`: only the id is known up front; the name
 * arrives with the detail query (shared with the page, so normally already cached).
 */
export function ObjectByIdCrumbs({ params: p, children }: CrumbsProps) {
  const objectId = Number(p.objectId)
  const q = useObjectById(Number(p.scanId), Number.isFinite(objectId) ? objectId : null)
  const s = q.data?.summary
  return children(s ? objectCrumbs(p.scanId ?? '', s) : [{ label: `#${p.objectId ?? ''}` }])
}
