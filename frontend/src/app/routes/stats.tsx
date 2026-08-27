import { useParams } from 'react-router'
import { StatsPage } from '@/features/stats/StatsPage'
import type { StatsPage as StatsPageId } from '@/lib/routes'

const PAGES = new Set(['tables', 'indexes', 'procs', 'missing-indexes'])

export default function StatsRoute() {
  const { page } = useParams()
  const id = (page && PAGES.has(page) ? page : 'tables') as StatsPageId
  return <StatsPage page={id} />
}
