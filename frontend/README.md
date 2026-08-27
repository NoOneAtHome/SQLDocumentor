# SQL Documentor — frontend

React 19 + Vite 8 + TypeScript SPA that browses SQL Documentor snapshots (schemas, tables, views,
routines, triggers, columns, indexes, keys, stats) and renders object- and column-level data
lineage as an interactive DAG.

Stack: Tailwind 4 + shadcn/ui (Radix), react-router 8 (data mode), TanStack Query 5 via
`openapi-fetch` / `openapi-react-query`, TanStack Table 9 (wrapped once in `DataGrid`),
`@xyflow/react` 12 + `elkjs` for the graph, shiki 4 for SQL, MSW 2 for the mock API.

## Commands

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on :5173, proxying `/api` and `/openapi.json` to `http://127.0.0.1:8000` |
| `npm run dev:mock` | Same, but served entirely from the MSW mock API (`VITE_MOCK_API=1`) — no backend needed |
| `npm test -- --run` | Vitest unit tests (pure lineage/graph modules, path builders, formatters, URL codec) |
| `npm run typecheck` | `tsc -b` |
| `npm run lint` | oxlint (type-aware) |
| `npm run build` | `tsc -b && vite build` → `dist/` (served by `sqldoc serve`) |
| `npm run api:types` | Regenerate `src/api/schema.d.ts` from the running backend's OpenAPI document |
| `npm run e2e` | Playwright smoke test (`e2e/smoke.spec.ts`), boots `dev:mock` automatically |
| `npm run ui:add <name>` | Add a shadcn component (Radix style) |

## Mock API

`src/test/msw/handlers.ts` implements the canonical API contract over an AdventureWorks-like
fixture (`src/test/msw/fixtures.ts`): in-scope `Sales`/`dbo` objects, cascaded `Person`/`Production`
objects, an external linked-server node, FK/catalog/trigger/parsed edges, column edges with
exact/inferred/unresolved confidences, a scan that runs through all phases in ~6 s, stats rows and
annotations. The same handlers back vitest (`src/test/msw/server.ts`) and the browser worker
(`public/mockServiceWorker.js`).

## Layout

```
src/
  api/        types.ts (contract mirror) · schema.d.ts (hand-authored OpenAPI paths until api:types) · client.ts ($api)
  app/        providers · router · error boundary · layouts (sidebar, topbar, breadcrumbs, scan layout) · routes
  components/ shared UI (ObjectTypeIcon, badges, ObjectLink, CodeBlock, DataGrid, states) + shadcn ui/
  features/   connections · scans · browser · search · objects (tabs) · annotations · lineage · stats
  lib/        routes.ts · format.ts · theme.tsx · shiki.ts · lineage-params.ts · constants.ts
  test/       vitest setup + MSW handlers/fixtures
```

Lineage explorer internals live in `features/lineage/graph`: `graph-state.ts` (expand/collapse/hide
bookkeeping with `addedBy` sets), `to-flow.ts` (state → React Flow nodes/edges), `sizes.ts`
(deterministic node sizes; ELK port y == Handle top), `layout.ts` (ELK layered, left→right).

## Conventions

- Object routes are name-based (`/s/:scanId/db/:db/:schema/:kind/:name[/tab]`) so links survive
  switching scans; every segment is `encodeURIComponent`-ed by `lib/routes.ts`.
- Scan-scoped queries are immutable: `staleTime: Infinity`, `gcTime: 30 min`.
- Annotation edits are optimistic on the composite object detail, then `/api/tags` is invalidated.
- Theme = `.dark` on `<html>` (localStorage `sqldoc.theme`, `system` default); object-type colours are
  CSS variables (`--obj-*`) used identically by tree icons, badges, node strips, minimap and legend.
