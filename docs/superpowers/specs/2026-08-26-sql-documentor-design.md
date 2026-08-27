# SQL Documentor — Implementation Plan

## Context

**Why:** There is no tool on hand that documents a Microsoft SQL Server estate the way the user wants: scoped to chosen schemas, but smart enough to pull in objects from other schemas/databases when a view/proc/function reaches across to them, with operational stats (row counts, sizes, index and proc usage) and — the centerpiece — a lineage DAG at object *and column* level that can be drilled up ("what feeds this?") and down ("what consumes this?").

**What:** A greenfield, local, single-user Python web app. FastAPI backend scans SQL Server via catalog views + DMVs, parses T-SQL bodies with `sqlglot` for column lineage, and stores each scan as an immutable snapshot in SQLite. A React/Vite SPA browses snapshots with a modern, dense-but-readable UI and a React Flow DAG explorer.

**Repo state:** `/Users/nooneathome/repos/SQLDocumentor` is empty (only `.claude/settings.local.json`). Not a git repo yet — `git init` is part of step 0.

## Decisions (confirmed with user)

| # | Topic | Decision |
|---|-------|----------|
| 1 | UI stack | FastAPI + React/Vite/TypeScript/Tailwind SPA |
| 2 | Deployment | Local single-user (`sqldoc serve` → localhost); no app login |
| 3 | Persistence | Each scan = immutable snapshot in local SQLite; UI reads snapshots, never live |
| 4 | Config | `sqldoc.yaml`: connections → databases → schemas. Passwords via `${ENV_VAR}` / `.env`. Secrets never in SQLite |
| 5 | SQL auth | SQL login **and** Windows/Kerberos integrated (trusted connection) |
| 6 | Cascade | Transitive, unlimited depth. Cascaded objects tagged `is_cascaded`. Cross-DB refs cascade only into databases configured on the same connection; otherwise `is_external` node (name only). Linked-server refs → external |
| 7 | Lineage | **Column-level from day one**, two layers: object edges from catalog (`sys.sql_expression_dependencies`, FKs, triggers — authoritative) + column edges from `sqlglot` T-SQL parsing of views, functions, procs (best-effort; confidence `exact`/`inferred`/`unresolved`) |
| 8 | Stats | Storage (rows, data/index size, partitions, compression); index usage (seeks/scans/lookups/updates, unused); proc/function exec stats; missing-index suggestions. Degrade gracefully without VIEW SERVER/DATABASE STATE |
| 9 | Annotations | User descriptions/notes/tags on objects & columns, stored in SQLite keyed by stable `object_key`; baseline from `MS_Description` extended properties |
| 10 | Dev DB | Existing Docker container `mssql` (SQL Server 2022, `localhost:1433`, **AdventureWorks2022** attached, `sqlcmd` at `/opt/mssql-tools18/bin` inside container) |

## Environment (verified)

- Python 3.14.7 + `uv` 0.9.5 (no poetry). Node 26.7 + npm 11 (no pnpm). Docker 29, arm64.
- **No ODBC driver / unixODBC installed.** Using `pyodbc` requires `brew install unixodbc` + `brew tap microsoft/mssql-release && brew install msodbcsql18`.
- All Python deps have cp314 wheels: pyodbc 5.3.0, pymssql 2.3.13, python-tds 1.17.1, sqlglot 30.17, SQLAlchemy 2.0.52, FastAPI 0.141, typer 0.27, pydantic-settings 2.15, alembic 1.19, pytest 9.1. `networkx` 3.6.1 excludes 3.14.1 only (we're on 3.14.7 — fine).
- npm: @xyflow/react 12.11, elkjs 0.12, react 19.2, vite 8.2, @tanstack/react-query 5.102, tailwindcss 4.3.

## Approaches considered

| | A. Catalog-first + relational edge tables (recommended) | B. In-memory graph per snapshot (networkx → JSON blob) | C. Live-query, no snapshots |
|---|---|---|---|
| Lineage storage | `object_dependencies` / `column_lineage` rows in SQLite; ego-graph via recursive CTE or BFS in Python over indexed rows | Whole graph pickled/JSON per scan; BFS in memory | Rebuilt per request from SQL Server |
| Pros | Queryable, diffable across scans, paged listings, scales to 10k+ objects, annotations join cleanly | Simplest graph code | Always current |
| Cons | More tables/models to write | Not queryable; memory-bound; re-serialize on every change; diffing awkward | Slow, no history (rejected by user in Q&A) |

**Choice: A.** SQLite already holds everything else; edge tables keep lineage joinable with objects/columns/annotations and make "latest scan" and future snapshot diffing trivial.

## Repository layout

```
SQLDocumentor/
  README.md  Makefile  sqldoc.example.yaml  .env.example  .gitignore
  backend/            # Python package `sqldoc` (uv project)  — see Backend section
  frontend/           # Vite + React + TS SPA                  — see Frontend section
  docs/superpowers/specs/2026-08-26-sql-documentor-design.md   # this design, committed with the repo
```

Two toolchains, one repo. `make dev-api` / `make dev-web` / `make build` / `make test`. Production: `sqldoc serve` runs uvicorn on :8000 and serves `frontend/dist`.

## Frontend design (React SPA)

### Library choices (all verified current)

| Concern | Choice | Note |
|---|---|---|
| DAG | `@xyflow/react` 12.11 + `elkjs` 0.12 (`layered`, `direction=RIGHT`) | Nodes are React components → node cards reuse Tailwind/shadcn. ELK supports **fixed-position ports** which is what column-level edges need; dagre/Cytoscape don't. |
| UI kit | Tailwind 4.3 + shadcn/ui — **choose Radix at `shadcn init`** (Base UI is now the default prompt; don't mix) | Tailwind v4: no `tailwind.config`, theme in CSS via `@theme inline`, `@custom-variant dark`. |
| Data | TanStack Query 5 via `openapi-fetch` + `openapi-react-query`; types generated by `openapi-typescript` from `/openapi.json` (commit `src/api/schema.d.ts`; `npm run api:types` regenerates) | Compile-time drift detection between API and UI. |
| Router | `react-router` 8 (data mode; `createBrowserRouter` + `RouterProvider` from `react-router/dom`, route-level `lazy`) | v8 is ESM-only, needs React ≥19.2.7 — pin `react@^19.2.7`. |
| Grids | TanStack Table 9 (`useTable` + `tableFeatures`) wrapped **once** in `components/data-grid/DataGrid.tsx`; `@tanstack/react-virtual` for long lists | shadcn DataTable docs are v8-flavoured; our wrapper isolates that. |
| SQL display | shiki 4 (`shiki/core` + JS regex engine, `@shikijs/langs/sql`, github-light/dark dual theme) — lazy-loaded on the Definition tab | **No `tsql` grammar exists**; `sql` is fine. Plain `<pre>` fallback for definitions > 200 KB. |
| Misc | `lucide-react`, `cmdk` (shadcn Command), `react-resizable-panels`, `sonner`, self-hosted `@fontsource-variable/inter` + `jetbrains-mono` | No global state lib: explorer state = URL params + `useReducer`; theme/sidebar = localStorage. |

### Routes (scan-scoped; objects addressed **by name** so links survive switching scans)

```
/                                              Home: connections, latest scan summary, warnings
/connections/:connId/scans                     Start scan, live progress, history
/s/:scanId                                     Scan overview (db/schema counts, type counts, warnings)
/s/:scanId/db/:db[/:schema[/:type]]            Database / schema overview + object grid (type tabs, search, sort)
/s/:scanId/db/:db/:schema/:type/:name[/tab]    Object detail; tabs: overview|columns|indexes|keys|parameters|definition|stats|lineage|notes
/s/:scanId/lineage?db&schema&type&name&col&level&dir&depth&types&schemas&cascaded&external
/s/:scanId/stats/{tables|indexes|procs|missing-indexes}
/settings
```
`:type` ∈ `table|view|proc|scalar_fn|inline_tvf|multi_tvf|trigger`. `encodeURIComponent` per segment (names like `[Order Details]`); backend route uses `{name:path}`.

Tabs per type: table → Overview·Columns·Indexes·Keys·Stats·Lineage·Notes; view → Overview·Columns·Indexes·Definition·Lineage·Notes; proc/scalar_fn → Overview·Parameters·Definition·Stats·Lineage·Notes; TVFs add Columns; trigger → Overview(parent, events, AFTER/INSTEAD OF)·Definition·Lineage·Notes; external → Overview callout·Lineage·Notes.

### Shell & navigation
shadcn `Sidebar` (280px, `⌘B` → icon rail): primary nav + lazily-loaded virtualised **object tree** (db → schema → type group w/ counts → objects; each level fetched on expand). Top bar: breadcrumbs, **scan switcher** (swaps `:scanId`, keeps path), `⌘K` search palette (debounced `/search`, groups Objects/Columns, `⌘↵` opens lineage), running-scan pill (polls progress), theme toggle.

### Lineage Explorer (the centerpiece)
- **Edge direction** = data flow (`source → target`). ELK `RIGHT` puts upstream left, focus centre, downstream right automatically.
- **Object node card** 240×64: type-coloured accent strip, icon + `schema.name` (mono), compact stat (`1.2M rows` / `4.3k execs`), badges (cascaded = dashed border, external = grey dotted, amber ⚠ when lineage issues). **Expand pills** `‹ +3` / `+5 ›` on each edge showing not-yet-loaded neighbours (from `node.more`); flip to `−` after expansion.
- **Interactions**: click → side panel; click pill → **expand in place** (`depth=1` fetch merged into canvas); `F`/panel → **refocus** (URL `focus` changes, surviving nodes keep positions as hints); double-click → detail (`zoomOnDoubleClick={false}`); right-click context menu (Focus/Expand up/down/Collapse/Hide/Open/Copy); hover highlights adjacent edges. Controls bar: direction Up/Both/Down, depth 1–5 (default 2), Objects/Columns toggle, filters (types, schemas, cascaded, external), Fit, Re-layout, legend — all in URL params.
- **Expand/collapse bookkeeping** (`graph/graph-state.ts` reducer): each node has `addedBy: Set<expansionId>`; collapse removes the id and drops nodes whose set empties (base ego-graph has permanent `"root"`). Hidden nodes stay with `hidden:true` so edge ids stay stable.
- **Column-level mode = table nodes with column ports** (option A). `ColumnTableNode` 260px wide: header + one 24px row per *participating* column (API returns only those; "show all N columns" toggle → `useUpdateNodeInternals`). Each row has `<Handle type="target" id="in:<col>">` / `<Handle type="source" id="out:<col>">`. Procs/triggers are **not nodes** in column mode — column edges go table→table with `via` (proc/view name) as edge label. Confidence styling: exact solid, inferred dashed, unresolved dotted amber.
- **Deterministic node sizes** (`graph/sizes.ts`: `HEADER_H + rows*ROW_H + footer`) so ELK gets exact dims and ports (`elk.portConstraints=FIXED_POS`, port `y = HEADER_H + i*ROW_H + ROW_H/2`) line up with Handles with no measure-then-layout round trip. Unit-test that both agree.
- **Layout options**: `elk.algorithm=layered, elk.direction=RIGHT, nodeNodeBetweenLayers=96, nodeNode=32, nodePlacement=BRANDES_KOEPF, crossingMinimization=LAYER_SWEEP, considerModelOrder=NODES_AND_EDGES, cycleBreaking=GREEDY`. Ignore ELK edge sections; React Flow draws edges (`getSmoothStepPath` object-level, `getBezierPath` column-level).
- **Stability/animation**: stable first-seen child order + `considerModelOrder`; new nodes seeded at parent position; `.is-animating` class for 300ms transform transition; refocus → `fitView({duration:300})`, expand → `fitView({maxZoom: getZoom()})` (never zoom in). Fallback: `INTERACTIVE` strategies with previous x/y.
- **Large graphs**: API `max_nodes` (default 200, hard max 1000) + `truncated`/`total` → banner "Showing 200 of 1,340" with "Depth −1"/"Filter types" actions; client accumulated cap 600; column mode `max_nodes=150`, ≤30 participating columns/node. RF perf: `onlyRenderVisibleElements`, module-scope `nodeTypes`, `React.memo` nodes, `nodesConnectable={false}`, minimap coloured by type.
- Edge colour by kind (catalog neutral, fk blue, trigger rose, parsed violet), legend `<Panel>` with per-kind toggles. `MiniLineage` (depth 1, static) embedded on every Overview tab.

### Visual direction
"Quiet, dense, precise" (Linear/Vercel density, dbt-Explorer-style graph). Neutral oklch greys, one indigo accent, 1px hairlines, 6px radius. Inter Variable (UI) + JetBrains Mono Variable (identifiers, SQL, numbers; `tabular-nums`). **Object-type colours** as CSS vars (`--obj-table` blue, `--obj-view` teal, `--obj-proc` violet, `--obj-function` amber, `--obj-trigger` red, `--obj-external` grey) exposed through `@theme inline`, used identically in tree icons, badges, node strips, minimap, legend. Light/dark via `.dark` on `<html>` (localStorage, `system` default) driving React Flow `colorMode` and shiki dual theme. States: layout-shaped skeletons, `placeholderData: keepPreviousData` on grid re-sorts, shadcn `Empty` with one action, inline `Alert` + Retry, route `ErrorBoundary`, "Not in this scan" 404 with scan-switch hint.

### Frontend file tree

```
frontend/
  index.html package.json vite.config.ts vitest.config.ts playwright.config.ts tsconfig*.json eslint.config.js components.json
  e2e/smoke.spec.ts
  src/
    main.tsx  index.css                     # tailwind, theme vars, obj colours, RF overrides, shiki dual theme
    app/ router.tsx providers.tsx error-boundary.tsx
         layouts/{AppLayout,ScanLayout}.tsx
         routes/{home,scans,scan-overview,schema-list,object-detail,lineage,stats,settings,not-found}.tsx
    api/ schema.d.ts (generated) client.ts ($api = openapi-react-query) types.ts
    features/
      connections/  ConnectionCard ConnectionDialog useConnections
      scans/        ScanProgressCard ScanHistoryTable StartScanDialog ScanSwitcher useScanProgress
      browser/      ObjectTree ObjectTreeNode useTreeData ObjectListGrid ObjectTypeTabs SchemaOverview
      objects/      ObjectHeader ObjectTabs object-types.ts  tabs/{Overview,Columns,Indexes,Keys,Parameters,Definition,Stats,Lineage,Notes}Tab.tsx  hooks/useObjectDetail
      lineage/      LineageExplorer LineageCanvas LineageControls LineageSidePanel LineageLegend MiniLineage
                    nodes/{ObjectNode,ColumnTableNode,ExpandPill}.tsx  edges/LineageEdge.tsx
                    graph/{graph-state,to-flow,layout,sizes}.ts  hooks/{useLineageGraph,useLineageParams}.ts
      stats/        StatsPage LargestTablesGrid UnusedIndexesGrid HotProcsGrid MissingIndexesGrid
      annotations/  DescriptionEditor NotesEditor TagInput useAnnotation
      search/       CommandPalette useSearch SearchResultItem
    components/ ui/ (shadcn)  data-grid/DataGrid.tsx  ObjectTypeIcon ObjectBadge ObjectLink CodeBlock KeyValueGrid StatCard PageHeader EmptyState ErrorState CopyButton RelativeTime
    lib/  routes.ts (path builders) format.ts theme.tsx shiki.ts utils.ts constants.ts
    test/ setup.ts msw/handlers.ts
```

### Dev/prod wiring
- `vite.config.ts`: `react()` + `@tailwindcss/vite`; alias `@ → src`; `server.proxy` for `/api` and `/openapi.json` → `http://127.0.0.1:8000`; `build.sourcemap: true`. Route `lazy()` + dynamic `import()` of elkjs/shiki give the chunk splits.
- FastAPI (≥0.141): `app.include_router(api_router, prefix="/api")` then `app.frontend("/", directory=FRONTEND_DIST, fallback="index.html", check_dir=False)` — API routes take priority; `fallback` serves `index.html` only for navigation requests.
- npm scripts: `dev`, `build` (`tsc -b && vite build`), `typecheck`, `lint`, `format`, `api:types`, `test` (vitest 4 + Testing Library + MSW), `e2e` (Playwright), `ui:add`.
- Client cache rules: scan-scoped queries `staleTime: Infinity, gcTime: 30min`; progress `refetchInterval: q => running ? 1000 : false`; annotation mutations optimistic `setQueryData` on the composite detail, then invalidate `/tags`.

### Frontend build order
(1) scaffold + shell + Home → (2) scans page + switcher + progress pill → (3) browser tree, `DataGrid`, object grid, ⌘K → (4) object detail (all tabs, shiki, annotations) → (5) lineage object-level (to-flow, ELK, ObjectNode, expand/collapse/refocus, truncation, MiniLineage) → (6) lineage column-level (ColumnTableNode ports, column endpoints) → (7) stats grids → (8) polish, Playwright smoke, README.

## Backend design (Python package `sqldoc`)

Facts below marked ✔ were verified by the design pass by running read-only queries against the live AdventureWorks2022 container and reading the sqlglot 30.17.0 source.

### Driver: `pyodbc` + Microsoft ODBC Driver 18
Kerberos/integrated auth is a hard requirement. msodbcsql18 is the only driver where it is one supported keyword (`Trusted_Connection=yes` → Kerberos via `kinit` ticket on macOS/Linux, SSPI on Windows). ✔ pymssql wheels are built without GSSAPI; python-tds needs python-gssapi/pykrb5 C extensions for Kerberos — no lighter than unixODBC. SQLAlchemy is used **only for SQLite**; SQL Server is raw DB-API.

- Install: `brew tap microsoft/mssql-release && brew install msodbcsql18` (pulls unixodbc); documented in README. `sqldoc connections test` reports `pyodbc.drivers()` and the negotiated `auth_scheme` (`SELECT auth_scheme FROM sys.dm_exec_connections WHERE session_id=@@SPID`).
- `mssql/driver.py`: `SqlServerDriver` Protocol (`connect(cfg, database, secret)`, `paramstyle`, `diagnostics()`) with a single `PyodbcDriver` impl. All catalog SQL uses `?` placeholders; `MssqlClient` uses only `execute/description/fetchall` — that is the whole swap surface if a pytds adapter is ever needed.
- Connection string: `DRIVER={ODBC Driver 18 for SQL Server};SERVER=tcp:{host},{port};DATABASE=…;Encrypt=yes|no;TrustServerCertificate=yes|no;APP=sqldoc;Connection Timeout=15` + (`UID`/`PWD` with `{}`-escaping) or `Trusted_Connection=yes`. `autocommit=True`. Never log `PWD`. For integrated auth `host` must be the FQDN matching the SPN.

### Config (`sqldoc.yaml`, pydantic models in `config/schema.py`, loader in `config/loader.py`)
```yaml
version: 1
storage: { sqlite_path: ./sqldoc.sqlite }
connections:
  - name: local-aw
    host: localhost
    port: 1433
    auth: { mode: sql, username: sa, password: "${MSSQL_SA_PASSWORD}" }   # or { mode: integrated }
    encrypt: true
    trust_server_certificate: true
    databases:
      - { name: AdventureWorks2022, schemas: [Sales, HumanResources] }
scan: { cascade_foreign_keys: true, include_triggers_of_cascaded_tables: true, collect_stats: true, parse_lineage: true }
```
`${VAR}` interpolated anywhere in string values; undefined var → error naming the key path; secrets wrapped in `SecretStr`. `.env` loaded at startup via pydantic-settings. Settings env: `SQLDOC_CONFIG`, `SQLDOC_DB`, `SQLDOC_HOST`, `SQLDOC_PORT`. Connections are **read-only in the API** (edited in YAML); the UI's "Add connection" shows the config path and example.

### Backend file tree
```
backend/
  pyproject.toml (uv; [project.scripts] sqldoc = "sqldoc.cli:app")  uv.lock  alembic.ini  README.md
  src/sqldoc/
    cli.py                  # typer: scan, serve, connections list|test, scans list|prune, db upgrade
    settings.py
    config/   schema.py loader.py
    mssql/    driver.py client.py identity.py catalog.py stats.py
              sql/*.sql     # one file per query, loaded via importlib.resources (reviewable T-SQL)
    scope/    cascade.py    # compute_closure(...) — pure, unit-testable
    lineage/  splitter.py schema_builder.py symbols.py rewrite.py engine.py confidence.py
    store/    db.py models.py writer.py repo.py migrations/ (alembic env + 0001_initial)
    graph/    traverse.py   # per-scan in-memory adjacency (LRU by scan_id); ego_graph()
    scan/     progress.py manager.py orchestrator.py
    api/      app.py deps.py schemas.py routers/{connections,scans,snapshot,lineage,annotations,search,stats}.py
  tests/
    unit/        test_config test_identity test_cascade test_splitter test_rewrite test_lineage_views test_lineage_procs test_lineage_triggers test_graph
    fixtures/    tsql/*.sql  fake_catalog.py
    integration/ conftest.py (marker `integration`; skip unless localhost:1433 answers and SQLDOC_TEST_PASSWORD set)
                 test_catalog_aw test_cascade_aw test_scan_aw test_lineage_aw test_api_aw
```

### Catalog extraction (`mssql/catalog.py`, one `.sql` per query) ✔ all executed on AW2022
One pyodbc connection per scan; `client.use_database(name)` runs `USE [db]` (escape `]`→`]]`) — catalog views are database-scoped so no 3-part names needed. `is_ms_shipped = 0` everywhere.

| Query | Source / key details |
|---|---|
| `objects` | `sys.objects` ⋈ `sys.schemas`; types `U V P PC FN IF TF FS FT TR TA SN SO TT`; table types also from `sys.table_types` |
| `columns` | `sys.columns` ⋈ `sys.types` (+ `computed_columns`, `default_constraints`, `identity_columns`); `max_length` is bytes (halve for nchar/nvarchar, `-1`=max) |
| `parameters` | `sys.parameters`; `parameter_id=0` with empty name = function return value |
| `indexes` / `index_columns` | `sys.indexes` (`index_id>0`, filter def, fill factor, disabled, data space) / `sys.index_columns` (key ordinal, desc, included) |
| `foreign_keys` / `foreign_key_columns` | `sys.foreign_keys` (referential actions, disabled, not trusted) / column pairs with names |
| `check_constraints` | `sys.check_constraints` |
| `extended_properties` | `MS_Description` for class 1 (object/column, minor_id=column_id or 0), 2 (parameter), 3 (schema), 7 (index) |
| `modules` | `sys.sql_modules.definition` (+ schema-bound, ansi/quoted flags); NULL for encrypted / no VIEW DEFINITION → `scan_warnings(no_definition)` |
| `triggers` / `synonyms` | `sys.triggers` (parent_class=1 DML only; events via `STRING_AGG` over `sys.trigger_events`, instead-of, disabled) / `sys.synonyms.base_object_name` |
| `dependencies` | `sys.sql_expression_dependencies WHERE referencing_class = 1` — all columns incl. `referencing_minor_id`, `referenced_server/database/schema/entity_name`, `referenced_id`, `is_caller_dependent`, `is_ambiguous` |
| probes | `sys.dm_os_sys_info.sqlserver_start_time`, `SERVERPROPERTY`, `@@SERVERNAME`; `HAS_PERMS_BY_NAME` for VIEW SERVER STATE / VIEW DATABASE STATE / VIEW DEFINITION per DB |

**Dependency-row interpretation rules (applied in order in `cascade.py`):** ✔
1. `referenced_id IS NOT NULL` → resolved same-DB object. `referencing_minor_id > 0` = a computed column/constraint references it (AW: `Sales.Customer.AccountNumber` → `dbo.ufnLeadingZeros`) — keep for column-level catalog edges.
2. `referenced_id IS NULL AND is_ambiguous = 1` → method-call/alias noise (XML `.value()`, hierarchyid methods, CTE names appear in `referenced_database_name`!) → dependency row with `resolution='ambiguous'`, **never a node**.
3. `referenced_server_name` set (≠ `@@SERVERNAME`) → `external` (4-part key).
4. `referenced_database_name` set → cross-DB: resolve in universe if that DB is configured on this connection (schema defaults `dbo`), else `external`.
5. `is_caller_dependent = 1` → try `dbo` in same DB → `resolution='caller_dependent'` (inferred) else `unresolved`.
6. `inserted`/`deleted` from a trigger → ignored.
7. Otherwise (temp tables, dropped objects) → `unresolved` row.

### Stats (`mssql/stats.py`) — each query in its own try/except → `scan_warnings(stats_unavailable)` and continue ✔
- **table_stats**: `sys.dm_db_partition_stats` ⋈ `sys.partitions` grouped by object: `row_count` = SUM where `index_id IN (0,1)`; `data_kb` = SUM(in_row + lob + row_overflow pages for index_id 0/1) × 8; `index_kb` = (SUM(used_page_count) − data pages) × 8; `reserved_kb`; `partition_count` = COUNT DISTINCT partition_number; `is_heap` = any index_id 0; compression min/max of `data_compression_desc` → `NONE|ROW|PAGE|COLUMNSTORE|MIXED`.
- **index_usage**: `sys.dm_db_index_usage_stats WHERE database_id = DB_ID()`; `is_unused` = nonclustered, non-PK, non-unique-constraint with no row or seeks+scans+lookups = 0 (`updates > 0` → "unused but maintained"). Show counters "since `sqlserver_start_time`".
- **proc_stats**: UNION ALL of `dm_exec_procedure_stats`, `dm_exec_function_stats`, `dm_exec_trigger_stats` (`database_id = DB_ID()`), grouped by object: SUM exec count/total elapsed/cpu/logical reads, MIN/MAX elapsed, MAX last_execution_time, MIN cached_time; `avg_elapsed_us` derived.
- **missing_indexes**: `dm_db_missing_index_details` ⋈ `_groups` ⋈ `_group_stats`; `improvement_measure = avg_total_user_cost × avg_user_impact × (user_seeks + user_scans)`; generate `suggested_ddl` string.

### Cascade algorithm (`scope/cascade.py`) — pure function over pre-fetched inputs
Inputs: universe (all objects of every configured DB, indexed case-insensitively by `(db, schema, name)` and `(db, object_id)`), dependency rows, FKs, triggers, synonyms, config. **FKs cascade** (`cascade_foreign_keys: true` default): an FK edge is meaningless without its target node/columns. Only *outgoing* references are followed; objects that merely reference in-scope objects are not pulled in (`include_dependents` noted as a later option).

```
seed   = objects in selected schemas → status in_scope
work   = deque(seed); visited = ∅
while work: oid = pop; skip if visited (cycles terminate here)
  for dep in deps[oid]: target = resolve (rules 1–7) →
      Resolved  → edge(kind=catalog, resolution, minor_id) ; enqueue(target)
      External  → externals[key]; edge(kind=catalog, external)
      Ignored   → pass ; Unresolved → unresolved.append
  if table: FK targets → edge(kind=fk); enqueue ; triggers (if in_scope or include_triggers_of_cascaded_tables) → edge(trigger→table); enqueue
  if synonym: resolve base name (1/2/3/4-part) → edge(kind=synonym); enqueue
enqueue(t): status.setdefault(t, cascaded); append if not visited
```
✔ AW with `schemas: [Sales]`: seed 19 tables + 7 views + 2 triggers; cascade pulls `Person.Person/Address/StateProvince/CountryRegion/EmailAddress/PersonPhone/…`, `HumanResources.Employee` (via `vSalesPerson`), `Production.TransactionHistory`, `dbo.uspLogError/uspPrintError` (via trigger `iduSalesOrderDetail`), `dbo.ufnGetAccountingStartDate/EndDate`, `dbo.ufnLeadingZeros` (computed column), FK targets like `Production.Product`, `Production.SpecialOffer`, and transitively their triggers/FKs. `Sales.vPersonDemographics` produces ambiguous rows but **no** external nodes.

### Column-level lineage pipeline (`lineage/`) ✔ sqlglot API verified from source
**Principle: analyze one object at a time, one level deep.** A view's column edges terminate at the columns of whatever it selects from (table *or* view); multi-hop lineage is assembled at query time by walking edges. Avoids sqlglot's fragile `sources=` name matching.

1. **Schema feeding** (`schema_builder.py`): one `MappingSchema(dialect="tsql", normalize=True)` per scan shaped `{database: {schema: {object: {column: type}}}}` for every table/view/TVF/table-type in the closure across all configured DBs (so 3-part names resolve; `SELECT *` expands to real column lists). Per-object pseudo tables: `inserted`/`deleted` (= parent table columns) for triggers; `#temp`/`@tablevar` from the symbol table.
2. **Statement splitting** (`splitter.py`): sqlglot only splits on `;` and typical T-SQL bodies have none. Walk `sqlglot.tokenize(body, read="tsql")` tracking paren depth and CASE depth; statement starts at depth 0 on DML/control keywords (`SELECT INSERT UPDATE DELETE MERGE WITH EXEC DECLARE SET IF ELSE WHILE BEGIN END RETURN TRY CATCH …`) with continuation rules (`SET` inside `UPDATE`; first `SELECT/WITH/EXEC/VALUES` after `INSERT`; `SELECT` after `UNION/EXCEPT/INTERSECT`; `MERGE` runs to `;`). Emit `(kind, start, end, text)` via `Token.start/end`; only DML goes to sqlglot; IF/WHILE nesting is flattened (every DML statement analyzed regardless of branch). Views/inline TVFs: `parse_one(definition)` → `exp.Create.expression` when it is an `exp.Query`; fallback to splitter after `AS`.
3. **Per-statement analysis** (`engine.py`): rename temp-table identifiers (`Identifier(temporary=True)` → `db="#temp"`, tsql parser strips `#` so they'd otherwise collide with real names); alias unnamed projections (`_col{i}`, else `SqlglotError`); `qualify(select, dialect="tsql", schema, catalog=<database>, db="dbo", validate_qualify_columns=False, identify=False)`; `lineage(None, q, schema, dialect="tsql", scope=build_scope(q))` → `dict[out_col → Node]`; DFS `Node.downstream` to leaves. Leaf `exp.Table` → `(catalog or db, schema or dbo, name)` → snapshot object + column; `db == "#temp"` → proc-local pseudo object; `*` or `exp.Placeholder` → unresolved. Target mapping: view/TVF output position → `sys.columns` ordinal (fallback by name + `lineage_issue(column_count_mismatch)`); proc top-level `SELECT`s without INTO → pseudo columns (`column_kind='resultset'`, `resultset_index`).
4. **DML rewrite** (`rewrite.py`) — every write becomes `(target, SELECT)`: `INSERT…SELECT` (column list / ordinal / temp cols); `INSERT…VALUES` → no column edges; `INSERT…EXEC p` → object edge `exec` + unresolved `p.* → T.*`; `UPDATE tgt SET a=e1 FROM … WHERE` → `SELECT e1 AS a … FROM <from incl. joins>` (alias resolved to real table); `MERGE` → `SELECT <set rhs AS col>, <values AS col> FROM tgt JOIN src ON cond`; `SELECT…INTO #t` → registers temp table with projection names; `OUTPUT…INTO @tv` → secondary target (inferred); `DELETE` → object-level write edge; `EXEC(@sql)`/`sp_executesql` → `lineage_issue(dynamic_sql)` + `has_dynamic_sql`. Symbol table (`symbols.py`): `CREATE TABLE #t`, `DECLARE @t TABLE (…)` (depth-aware scan; sqlglot may yield `exp.Command`), `SELECT INTO`, bare `INSERT INTO #t` (inferred cols). Temp tables persist as pseudo-objects (`kind='temp_table'`, `parent_object_id`=owner) so the UI can show the hop; graph option `collapse_temp` composes through them.
5. **Object kinds**: view → one query; inline TVF → the `RETURN (SELECT…)`; multi-statement TVF → body + `@ret` re-targeted to the function's own columns; scalar fn → object edges + best-effort `RETURN_VALUE` pseudo column (inferred); trigger → body with `inserted/deleted` re-targeted to the parent table (exact for `inserted`). Computed column definitions (`sys.computed_columns`) parsed as expressions → intra-table edges (`transform='computed'`).
6. **Confidence** (`confidence.py`): `exact` = every path node is a column/alias-of-column, leaf object+column known, no default-schema/caller-dependent assumption; `inferred` = any expression/function/CASE/aggregate/CAST on the path, or unknown column on known object, or caller-dependent/ambiguous resolution, or through an inferred temp table, or `OUTPUT INTO`; `unresolved` = Placeholder/`*`, unknown table, `INSERT…EXEC`, dynamic SQL, `OPENQUERY/OPENROWSET/OPENJSON/OPENXML`. Each edge stores `expression_sql`, `statement_index`, `statement_kind`, `transform` (`passthrough|expression|aggregate|star|temp|pseudo|computed`), `via`.
7. **Failure isolation**: per statement, catch `ParseError/OptimizeError/SqlglotError/RecursionError/Exception` → `lineage_issues(object, statement_index, kind, message, snippet)`; catalog edges always remain. Per-object time budget 20s and `max_definition_chars` 500KB → `skipped`. Scan summary reports `lineage_coverage`.
8. **Known-weak T-SQL** (expect issue rows, covered by fixtures): `DECLARE @t TABLE`, cursors, `SELECT @v = col`, XML/hierarchyid methods, `FOR XML/JSON`, PIVOT/UNPIVOT, `OPENJSON/STRING_SPLIT` in `CROSS APPLY`, `db..table`, `$IDENTITY`, `AT TIME ZONE`, `CONTAINS/FREETEXT` (AW `uspSearchCandidateResumes`).

### SQLite snapshot schema (`store/models.py`, SQLAlchemy 2.0 declarative, Alembic from day one)
Every scan is an **immutable snapshot**: all snapshot tables carry `scan_id` (FK `ON DELETE CASCADE`) and are never updated after finish (except `scans.status`). Latest = newest `succeeded` scan per connection. `sqldoc scans prune --keep N` (default retention 5). Annotations/tags are **not** scan-scoped; they key on `object_key`.

Identity: `object_key = "{connection}|{database}|{schema}|{name}"` (catalog case, compared `COLLATE NOCASE`); `column_key = object_key + "|" + column`; external `"external|{server}|{database}|{schema}|{name}"`; temp `owner_key + "|#" + name`.

| Table | Key columns |
|---|---|
| `scans` | connection_name, status (running/succeeded/failed/cancelled), phase, started/finished_at, server_name/version/edition, server_start_time, config_json (secrets stripped), summary_json, error |
| `databases` | scan_id, name, database_id, collation, compatibility_level, is_configured, selected_schemas_json, has_view_definition, has_view_database_state |
| `objects` | scan_id, database_id (null for external), object_key, schema_name, name, **kind** (`table view procedure scalar_function inline_tvf table_function clr_function trigger synonym sequence table_type temp_table external`), sql_object_id, **scope** (`in_scope cascaded external`), parent_object_id (trigger→table, temp→owner), external_server/database, base_object_name, create/modify_date, description, definition, is_schema_bound, is_instead_of_trigger, trigger_events, is_disabled, has_dynamic_sql, lineage_status (`ok partial failed skipped n/a`) |
| `columns` | scan_id, object_id, column_key, column_id, ordinal, name, column_kind (`column resultset return_value`), resultset_index, type fields, nullability/identity/computed/default/collation, description |
| `parameters`, `indexes`, `index_columns`, `foreign_keys`, `foreign_key_columns`, `check_constraints` | as per catalog queries; FK rows reference `objects.id`/`columns.id` |
| `object_dependencies` | scan_id, source_object_id, target_object_id (null if unresolved), edge_kind (`catalog fk trigger synonym parsed_read parsed_write parsed_exec`), resolution (`resolved caller_dependent ambiguous external unresolved`), is_ambiguous, is_caller_dependent, is_schema_bound, referencing_column_id, referenced_name |
| `column_lineage` | scan_id, source_object_id, source_column_id/name, target_object_id, target_column_id, confidence, transform, statement_index, statement_kind, expression_sql, via |
| `table_stats`, `index_usage`, `proc_stats`, `missing_indexes` | per stats queries (+ derived `is_unused`, `avg_elapsed_us`, `improvement_measure`) |
| `lineage_issues` | scan_id, object_id, statement_index, kind (`parse_error qualify_failed dynamic_sql unsupported column_count_mismatch skipped timeout`), message, snippet |
| `scan_warnings` | scan_id, phase, database_name, code, message, detail |
| `annotations` | target_kind (object/column), target_key (NOCASE unique), description, notes, timestamps |
| `tags`, `tag_assignments` | name (NOCASE unique), color / tag_id, target_kind, target_key |
| `meta` | key/value |

Indexes on `(scan_id, kind)`, `(scan_id, schema_name)`, `(scan_id, source_object_id)`, `(scan_id, target_object_id)`, `(scan_id, source_column_id)`, `(scan_id, target_column_id)`. Pragmas: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. `sqldoc serve`/`scan` run `alembic upgrade head` at startup.

### Scan orchestration (`scan/`)
`ScanManager.start(connection)` → `scans` row + daemon `threading.Thread` → `run_scan`; single-flight per connection (409 if running); `cancel` Event checked between objects/queries. Phases, each committing before the next (a crash leaves a diagnosable `failed` scan):

`connect` (server info, permission probes) → `enumerate` (objects/triggers/synonyms per DB → universe) → `cascade` (deps + FKs per DB → `compute_closure`) → `extract` (all detail queries per DB, filtered in Python to closure ids; external nodes written) → `stats` (skipped with warning if `collect_stats=false` or permissions missing) → `lineage` (build MappingSchema; views → TVFs → procs → triggers → scalar fns; computed columns; per-object progress) → `finalize` (summary_json, status).

Progress object `{scan_id, status, phase, phase_index, phase_count, current, total, message, started_at, updated_at, warnings, errors}` served from memory while running, from the `scans` row afterwards. ✔ Estimated AW2022 full scan ≈ 5–10s (≈20 catalog queries < 100ms each; 41 modules / 79KB T-SQL lineage ≈ 2–5s). A 5k-object DB: catalog 10–20s, lineage 1–4 min single-threaded — `ProcessPoolExecutor` for the lineage phase is the later optimization (objects are independent).

## API contract (canonical — reconciled from both design passes)

All under `/api`, JSON, FastAPI default `{detail}` errors, lists `{items, total, limit, offset}`. Snapshot endpoints are scan-scoped and immutable → `Cache-Control: max-age=86400`; client `staleTime: Infinity`. Endpoints are sync `def` (uvicorn threadpool); the scan thread never shares a session with handlers. OpenAPI at `/openapi.json` feeds `npm run api:types`.

**Connections** (read-only; edited in YAML)
- `GET /api/connections` → `{items: [{name, host, port, auth_mode, databases: [{name, schemas}], latest_scan: ScanSummary|null, running_scan_id|null}]}`
- `POST /api/connections/{name}/test` → `{ok, server_name, version, edition, auth_scheme, driver, can_view_server_state, databases: [{name, reachable, can_view_definition, can_view_database_state}], error?}`
- `GET /api/config` → sanitized config + `config_path`, `sqlite_path`; `GET /api/health` → `{ok, version, db_path}`

**Scans**
- `GET /api/connections/{name}/scans?limit&offset` → `ScanSummary[]`; `POST /api/connections/{name}/scans` `{collect_stats?, parse_lineage?}` → `202 {scan_id}` (409 if running)
- `GET /api/scans/{id}` → `ScanSummary` + progress `{phase, phase_index, phase_count, current, total, message, updated_at}` + `warnings[]`; `POST /api/scans/{id}/cancel`; `DELETE /api/scans/{id}`
- `GET /api/scans/{id}/summary` → `{databases: [{name, is_configured, schemas: [{name, is_selected, counts_by_kind}]}], counts, lineage_coverage, warnings_summary: {lineage_issues, unused_indexes, missing_index_suggestions, external_refs}}`
- `ScanSummary {id, connection, status, started_at, finished_at, duration_ms, options, counts: {databases, schemas, tables, views, procedures, functions, triggers, columns, edges_object, edges_column, lineage_issues}, error?}`

**Catalog**
- `GET /api/scans/{id}/objects?db&schema&kind&scope&q&tag&has_issues&sort=name|kind|rows|size|modified&order&limit&offset` → `ObjectSummary[]`
- `GET /api/scans/{id}/objects/{object_id}` → `ObjectDetail` (composite; one round trip renders the whole page); `GET /api/scans/{id}/objects/lookup?db&schema&name` → same (name-based, used by SPA routes; query params sidestep `/` in names)
- `GET /api/scans/{id}/objects/{object_id}/definition` → `{definition, length, has_dynamic_sql}` (split out: can be hundreds of KB)
- `GET /api/scans/{id}/search?q&kinds=object,column,definition&limit=20` → `{objects: [ObjectSummary & {match: {field, snippet}}], columns: [{object: ObjectSummary, column, data_type}]}` (`LIKE … COLLATE NOCASE`; FTS5 later if needed)

```ts
ObjectSummary { id, object_key, db, schema, name, kind, scope, description?, annotation_description?, tags: string[],
                row_count?, total_size_kb?, exec_count?, modified_at?, lineage_status, has_lineage_issues }
ObjectDetail  { summary, sql_object_id, ms_description, created_at, modified_at, parent?: {id, schema, name, kind},
                columns: Column[], parameters: Parameter[], indexes: Index[],
                keys: { primary_key?, unique_constraints[], foreign_keys_out[], foreign_keys_in[], check_constraints[] },
                triggers: [{id, name, events, is_instead_of, is_disabled}],
                stats: TableStats | ExecStats | null, missing_indexes: MissingIndex[],
                dependencies: { uses: DepRef[], used_by: DepRef[] },      // object-level, one hop
                lineage_counts: { upstream, downstream, columns_with_lineage },
                lineage_issues: [{kind, statement_index?, message, snippet?}],
                annotation: Annotation|null, column_annotations: Record<string, Annotation> }
Column { id, ordinal, name, column_kind, type_display, is_nullable, is_identity, is_computed, computed_definition?, default_definition?,
         collation?, in_primary_key, fk_to?: {object_id, schema, name, column}, ms_description?, description?, lineage: {upstream, downstream} }
Index  { id, name, type_desc, is_unique, is_primary_key, is_unique_constraint, key_columns: [{name, desc}], included_columns, filter?, is_disabled,
         usage: {seeks, scans, lookups, updates, last_seek, last_scan, last_lookup, last_update} | null, is_unused, description? }
TableStats { row_count, data_kb, index_kb, reserved_kb, partition_count, is_heap, compression, stats_as_of }
ExecStats  { exec_count, total_ms, avg_ms, min_ms, max_ms, total_cpu_ms, last_exec_at, cached_since, since_server_start }
MissingIndex { equality_columns, inequality_columns, included_columns, user_seeks, user_scans, avg_cost, avg_impact, improvement_measure, suggested_ddl }
```

**Lineage**
- `GET /api/scans/{id}/lineage/objects?focus={object_id}&direction=up|down|both&depth=1..5&kinds&schemas&edge_kinds&include_cascaded=true&include_external=true&max_nodes=200` → `LineageGraph`
- `GET /api/scans/{id}/lineage/columns?focus={object_id}&column={name}?&direction&depth&min_confidence=unresolved|inferred|exact&collapse_temp=false&max_nodes=150` → `ColumnLineageGraph` (omit `column` → seed with all lineage-bearing columns of the object)
- `GET /api/scans/{id}/lineage/objects/{object_id}/columns` → `[{column_id, name, upstream_count, downstream_count, confidences: {exact, inferred, unresolved}}]`
- `GET /api/scans/{id}/lineage/summary` → `{objects, edges_by_kind, column_edges_by_confidence, lineage_coverage, objects_with_issues, top_hubs[]}`; `GET /api/scans/{id}/lineage/issues?limit&offset`

```ts
LineageGraph { focus: 'o:123', nodes: LineageNode[], edges: LineageEdge[], truncated, total }
LineageNode  { id: 'o:123', object_id, db, schema, name, kind, scope, hop /* <0 up, 0 focus, >0 down */, row_count?, exec_count?,
               has_lineage_issues, more: { upstream: number, downstream: number } /* neighbours not returned → expand pills */ }
LineageEdge  { id, source, target, kind: 'catalog'|'fk'|'trigger'|'synonym'|'parsed_read'|'parsed_write'|'parsed_exec', resolution, detail? }
ColumnLineageGraph { focus: {object_id, column?}, nodes: ColumnLineageNode[], edges: ColumnLineageEdge[], truncated, total }
ColumnLineageNode  { ...LineageNode minus stats, columns: [{column_id, name, data_type?}] /* participating only */, column_count_total }
ColumnLineageEdge  { id, source, source_column, target, target_column, confidence, transform, via_object_id?, via_name?, expression? }
```
Traversal (`graph/traverse.py`): per-scan adjacency loaded once (LRU by scan_id), BFS with hop limit; priority when capping = hop distance, non-external, degree; `truncated`/`total` reported. Column mode groups column nodes by object server-side; procs/triggers appear only as `via` on edges.

**Stats grids** (`?sort&order&limit&offset&db&schema`): `GET /api/scans/{id}/stats/tables`, `/stats/indexes?unused=true`, `/stats/procs`, `/stats/missing-indexes` → items `{object: ObjectSummary, ...row}`.

**Annotations & tags** (connection-scoped, survive rescans)
- `PUT /api/annotations` `{connection, db, schema, name, column?, description?, notes?, tags?}` → `Annotation` (upsert; `null` clears); `DELETE /api/annotations` (same key); `GET /api/annotations?connection&tag&q&limit&offset`; `GET /api/tags?connection` → `[{tag, color, count}]`
- Payloads always carry both `ms_description` (catalog) and `description` (user); UI shows the user's when present.

## Build order (each step leaves something runnable; TDD for the pure modules)

0. **Bootstrap**: `git init`, `.gitignore`, README, Makefile, `sqldoc.example.yaml`, `.env.example`; write the design spec to `docs/superpowers/specs/2026-08-26-sql-documentor-design.md`; `brew install msodbcsql18` (needs user's OK — system package); `uv init backend`, Vite scaffold `frontend` (react-ts), Tailwind 4, shadcn init (**Radix**), router 8, TanStack Query, openapi-typescript.
1. **Backend config + driver**: `config/` (+ `test_config`), `mssql/driver.py`, `client.py`, `cli connections list|test` → verified against the container with SQL auth.
2. **Catalog → SQLite**: `identity.py`, `catalog.py` + `sql/*.sql`, `store/models.py`, `db.py`, Alembic `0001`, `writer.py`, `orchestrator.py` (no cascade/stats/lineage yet), `sqldoc scan` → first snapshot; `test_catalog_aw` counts.
3. **Cascade**: `scope/cascade.py` TDD with `fake_catalog.py`; wire in; `test_cascade_aw` (`[Sales]` scenario).
4. **API + scan manager**: `api/app.py`, routers connections/scans/snapshot/stats(objects)/search, object-level `lineage/objects` (catalog/fk/trigger edges), `scan/manager.py`, `progress.py`; `app.frontend()` mount.
5. **Frontend shell → browser → detail** (frontend steps 1–4): scaffold, shell, Home, scans page + progress pill, tree, `DataGrid`, object grid, ⌘K, object detail tabs incl. shiki Definition; annotations routers + Notes tab.
6. **Stats**: `mssql/stats.py` with degradation, stats in detail + stats grids + Stats pages.
7. **Column lineage backend**: `splitter.py` → `schema_builder.py` → `engine.py` (views) → `rewrite.py`/`symbols.py` (procs/TVFs/triggers) → `confidence.py` → column endpoints; `test_lineage_views/procs/triggers` + `test_lineage_aw`.
8. **Lineage Explorer**: object-level (to-flow, ELK, ObjectNode, expand/collapse/refocus, truncation banner, side panel, MiniLineage) → column-level (ColumnTableNode ports, column endpoints, confidence styling).
9. **Polish**: `scans prune`, empty/error states, shortcuts, Playwright smoke, README install docs (driver per OS, Kerberos `kinit` note), `uv build`.

## Verification

- **Unit** (`cd backend && uv run pytest tests/unit`): config interpolation/secrets; multipart name parsing; cascade (seeding, transitive, cycles, FK on/off, cross-DB configured vs external, ambiguous rows → no nodes, caller-dependent → dbo, synonyms); splitter (semicolon-free bodies, CASE/END, TRY/CATCH, UPDATE…SET, INSERT…SELECT, UNION, MERGE, `;WITH`, `DECLARE @t TABLE`, dynamic SQL); rewrite (UPDATE FROM alias, MERGE, INSERT positional, SELECT INTO, OUTPUT INTO); lineage fixtures (passthrough, alias, expression → inferred, aggregate, CTE, derived table, UNION, `SELECT *` with/without schema, 3-part names, UDF, XML `.value()`, view-over-view stops at inner view; temp-table chain, table variable, INSERT…EXEC, result-set columns, statement isolation; trigger inserted/deleted); graph BFS/truncation. Frontend: vitest for `graph-state`, `to-flow`, `sizes`/ELK port agreement, `format`, `useLineageParams`.
- **Integration** (`uv run pytest -m integration`, needs `SQLDOC_TEST_PASSWORD` = the container's SA password): catalog counts on AW2022 (749 columns, 90 FKs, 175 indexes, 324 dependency rows, 1008 object/column descriptions); `[Sales]` cascade set incl. `Person.Person`, `HumanResources.Employee`, `dbo.uspLogError`, `dbo.ufnLeadingZeros`, `Production.Product`; no external nodes from `vPersonDemographics`; column lineage `Sales.vIndividualCustomer.FirstName ← Person.Person.FirstName` (exact), `AddressLine1 ← Person.Address.AddressLine1`, `vSalesPersonSalesByFiscalYears` (PIVOT) doesn't crash, `dbo.ufnGetContactInformation` (multi-TVF) edges from `Person.Person`, `Sales.iduSalesOrderDetail` writes `Production.TransactionHistory` from `inserted.*`; `lineage_coverage ≥ 0.8`; full scan via `ScanManager` → every router once via TestClient; second scan → latest resolution + annotations survive by `object_key`.
- **End-to-end**: `make dev-api` + `make dev-web`; in the browser (Playwright MCP or manual): Home shows `local-aw` → Scan now → progress reaches `succeeded` (~5–10s) → tree to `Sales.vIndividualCustomer` → Columns tab rows → Lineage tab renders nodes → full explorer → click `+n` pill expands → Columns toggle shows column ports with edges to `Person.Person` → Stats pages list largest tables / missing indexes → add a tag and description, rescan, confirm they persist. Playwright smoke (`npm run e2e`) automates the same path against a fixture SQLite (`SQLDOC_DB=fixtures/demo.sqlite`).
- **Production path**: `npm run build` → `sqldoc serve --open` serves `frontend/dist` on :8000 with API routes taking priority.

## Follow-ups (explicitly out of v1)
Snapshot diffing between scans; static HTML/Markdown export; write-back of descriptions to `MS_Description`; `include_dependents` cascade option; `ProcessPoolExecutor` lineage phase; Azure AD auth; elkjs web worker (only if measured); FTS5 search.



## Implementation notes (deviations from the plan)

- **Driver:** the dev machine (macOS 27 / outdated Xcode CLT) cannot build `unixodbc`, and
  `pyodbc`'s macOS wheel dynamically links Homebrew's `libodbc`, so `pyodbc` became an
  optional extra (`uv sync --extra odbc`) and `pymssql` (bundled FreeTDS) is the base
  driver. `driver: auto` prefers pyodbc when the Microsoft ODBC driver is present;
  integrated auth requires it and fails with a clear message otherwise.
- **T-SQL splitting:** sqlglot's tsql tokenizer puts `END`, `FETCH`, `PRINT`-style commands
  into "command mode" and swallows the remainder of the statement into one STRING token;
  the splitter re-tokenizes those remainders recursively. `IF UPDATE(col)` predicates in
  triggers are distinguished from UPDATE statements by the following `(`.
- **Object reads** are collected from the original (pre-qualification) query so unresolved
  names keep their spelling; column-level `via_object_id` is set on edges written by
  procedures/triggers into tables.
- **Scalar functions** get lineage only when `RETURN (SELECT ...)` is used directly;
  variable-flow (`SELECT @v = col ... RETURN @v`) is a follow-up.
- `sqldoc.yaml` `${VAR}` references must be quoted inside `{ }` flow mappings.
- **API contract refinements:** path parameters are named `{scan_id}` / `{object_id}` / `{name}`
  in OpenAPI (the SPA's `openapi-fetch` templates must match literally); enum-valued fields
  (`kind`, `scope`, `confidence`, `edge_kind`, `resolution`, `transform`, `lineage_status`,
  `column_kind`, scan `status`/`phase`, `auth_mode`, `driver`, issue `kind`) are declared as
  `Literal`s so the generated TypeScript gets string-literal unions. `GET /api/config` returns
  `{config_path, sqlite_path, config}`; `GET /api/tags` and
  `GET /api/scans/{scan_id}/lineage/objects/{object_id}/columns` return bare arrays; every
  other list uses the `{items,total,limit,offset}` envelope. Scan-scoped GETs whose payload
  embeds user annotations send `Cache-Control: no-cache`; annotation-free payloads
  (definition, lineage, scan summary) are cached for a day — but only once the scan is
  terminal; while a scan is running they are `no-cache` and the in-process graph cache is
  bypassed, so partial lineage never sticks.
- **Layout:** confidence classification lives inline in `lineage/engine.py` (`_edge`) rather
  than a separate `confidence.py`, and the T-SQL lineage fixtures are inline strings in
  `tests/unit/test_lineage_*.py` rather than `tests/fixtures/tsql/*.sql`.
