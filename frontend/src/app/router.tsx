import { createBrowserRouter } from 'react-router'
import { routePatterns, routes } from '@/lib/routes'
import { type RouteHandle, objectCrumbs } from './crumbs'
import { RouteErrorBoundary } from './error-boundary'
import { AppLayout } from './layouts/AppLayout'
import { ObjectByIdCrumbs } from './layouts/ObjectByIdCrumbs'
import { ScanLayout } from './layouts/ScanLayout'
import { NotFoundPage } from './routes/not-found'
import { RouteFallback } from './routes/fallback'

export type { Crumb, RouteHandle, RouteParams } from './crumbs'

const handle = (fn: RouteHandle['crumbs']): RouteHandle => ({ crumbs: fn })

export const router = createBrowserRouter([
  {
    path: '/',
    Component: AppLayout,
    ErrorBoundary: RouteErrorBoundary,
    HydrateFallback: RouteFallback,
    children: [
      {
        index: true,
        lazy: () => import('./routes/home').then((m) => ({ Component: m.default })),
      },
      {
        path: 'connections/:connId/scans',
        lazy: () => import('./routes/scans').then((m) => ({ Component: m.default })),
        handle: handle((p) => [{ label: p.connId ?? 'Connection' }, { label: 'Scans' }]),
      },
      {
        path: 'settings',
        lazy: () => import('./routes/settings').then((m) => ({ Component: m.default })),
        handle: handle(() => [{ label: 'Settings' }]),
      },
      {
        path: 's/:scanId',
        Component: ScanLayout,
        ErrorBoundary: RouteErrorBoundary,
        handle: handle((p) => [{ label: `Scan #${p.scanId}`, to: routes.scan(p.scanId ?? '') }]),
        children: [
          {
            index: true,
            lazy: () => import('./routes/scan-overview').then((m) => ({ Component: m.default })),
          },
          {
            path: 'db/:db',
            lazy: () => import('./routes/schema-list').then((m) => ({ Component: m.default })),
            handle: handle((p) => [{ label: p.db ?? '', to: routes.db(p.scanId ?? '', p.db ?? '') }]),
          },
          {
            path: 'db/:db/:schema',
            lazy: () => import('./routes/schema-list').then((m) => ({ Component: m.default })),
            handle: handle((p) => [
              { label: p.db ?? '', to: routes.db(p.scanId ?? '', p.db ?? '') },
              { label: p.schema ?? '', to: routes.schema(p.scanId ?? '', p.db ?? '', p.schema ?? '') },
            ]),
          },
          {
            path: 'db/:db/:schema/:kind',
            lazy: () => import('./routes/schema-list').then((m) => ({ Component: m.default })),
            handle: handle((p) => [
              { label: p.db ?? '', to: routes.db(p.scanId ?? '', p.db ?? '') },
              { label: p.schema ?? '', to: routes.schema(p.scanId ?? '', p.db ?? '', p.schema ?? '') },
              { label: p.kind ?? '' },
            ]),
          },
          {
            path: 'db/:db/:schema/:kind/:name/:tab?',
            lazy: () => import('./routes/object-detail').then((m) => ({ Component: m.default })),
            handle: handle((p) => objectCrumbs(p.scanId ?? '', { db: p.db, schema: p.schema, name: p.name ?? '' })),
          },
          {
            // Same page, addressed by snapshot-local id — the only address external objects have.
            path: routePatterns.objectById,
            lazy: () => import('./routes/object-detail').then((m) => ({ Component: m.default })),
            handle: { Crumbs: ObjectByIdCrumbs } satisfies RouteHandle,
          },
          {
            path: 'lineage',
            lazy: () => import('./routes/lineage').then((m) => ({ Component: m.default })),
            handle: handle(() => [{ label: 'Lineage' }]),
          },
          {
            path: 'stats/:page?',
            lazy: () => import('./routes/stats').then((m) => ({ Component: m.default })),
            handle: handle((p) => [{ label: 'Stats', to: routes.stats(p.scanId ?? '', 'tables') }]),
          },
        ],
      },
      { path: '*', Component: NotFoundPage },
    ],
  },
])
