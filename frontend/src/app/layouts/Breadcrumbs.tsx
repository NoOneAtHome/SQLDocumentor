import { Fragment } from 'react'
import { Link, type UIMatch, useMatches } from 'react-router'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import type { Crumb, RouteHandle, RouteParams } from '../crumbs'

const asHandle = (m: UIMatch): RouteHandle | undefined => m.handle as RouteHandle | undefined

export function Breadcrumbs() {
  const matches = useMatches().filter((m) => {
    const h = asHandle(m)
    return !!(h?.crumbs || h?.Crumbs)
  })
  if (matches.length === 0) return null
  return (
    <Breadcrumb className="min-w-0">
      <BreadcrumbList className="flex-nowrap gap-1 text-[12.5px] sm:gap-1">
        {matches.map((m, i) => {
          const h = asHandle(m)!
          const params = m.params as RouteParams
          const pos = { first: i === 0, last: i === matches.length - 1 }
          if (h.Crumbs) {
            // Data-dependent crumbs come from a route-provided component (keyed by the stable route id).
            const Dynamic = h.Crumbs
            return (
              <Dynamic key={m.id} params={params}>
                {(crumbs) => <CrumbItems crumbs={crumbs} {...pos} />}
              </Dynamic>
            )
          }
          return <CrumbItems key={m.id} crumbs={h.crumbs!(params)} {...pos} />
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

/** One route's crumbs. A separator precedes every crumb except the very first of the trail. */
function CrumbItems({ crumbs, first, last }: { crumbs: Crumb[]; first: boolean; last: boolean }) {
  return (
    <>
      {crumbs.map((c, i) => {
        const isPage = (last && i === crumbs.length - 1) || !c.to
        return (
          <Fragment key={`${c.label}-${i}`}>
            {!(first && i === 0) && <BreadcrumbSeparator className="[&>svg]:size-3" />}
            <BreadcrumbItem className="min-w-0">
              {isPage ? (
                <BreadcrumbPage className="truncate font-medium">{c.label}</BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild className="truncate">
                  <Link to={c.to!}>{c.label}</Link>
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
          </Fragment>
        )
      })}
    </>
  )
}
