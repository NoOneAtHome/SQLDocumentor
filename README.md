# SQL Documentor

A local web app that documents a Microsoft SQL Server estate: schemas, tables, views,
stored procedures, functions, triggers, columns, indexes, foreign keys, row counts and
usage stats — plus **object- and column-level lineage** you can drill up ("what feeds
this?") and down ("what consumes this?") in an interactive DAG.

Scans are scoped to the schemas you select, but anything an in-scope view / proc /
function / trigger / FK reaches in another schema (or another configured database) is
pulled in transitively and tagged `cascaded`. Each scan is stored as an immutable
snapshot in a local SQLite file; the UI reads snapshots, never the live server.

## Layout

| Path | What |
|---|---|
| `backend/` | Python package `sqldoc` (FastAPI API, scanner, sqlglot-based lineage engine, Typer CLI). `uv` project. |
| `frontend/` | React + Vite + TypeScript SPA (Tailwind, shadcn/ui, React Flow + ELK for the lineage DAG). |
| `docs/superpowers/specs/` | The design spec this was built from. |
| `sqldoc.example.yaml` | Example configuration — copy to `sqldoc.yaml`. |
| `.env.example` | Example secrets file — copy to `.env`. |

## Prerequisites

| Tool | Version | Used for |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | any recent | Python environment + the `sqldoc` CLI. Downloads Python automatically if none is installed. |
| Python | 3.12 or newer | backend (`uv sync` fetches one if needed) |
| Node.js | 22 LTS or newer (Vite needs `^20.19 \|\| >=22.12`) | building the SPA — only needed once, or for UI development |
| Git | any | getting the code |
| Microsoft ODBC Driver 18 | 18.x | **optional** — only for `auth.mode: integrated` (Kerberos / Windows auth) |

Both SQL Server drivers (`pymssql`, `pyodbc`) ship prebuilt wheels for macOS (arm64 +
x86_64) and Windows (x64) on Python 3.12–3.14, so no compiler is needed on either OS.

The end-to-end flow is the same everywhere: install tools → `uv sync` → copy and edit
`sqldoc.yaml` + `.env` → `sqldoc connections test` → `sqldoc scan` → build the UI once →
`sqldoc serve --open`. The two sections below spell it out per platform.

## Setting up on macOS

Tested on Apple Silicon (macOS 15+). Everything runs in Terminal / zsh.

```bash
# 1. Tools (Homebrew: https://brew.sh)
xcode-select --install                    # git + Apple Command Line Tools (skip if already installed)
brew install uv node                      # or: curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Get the code
git clone <repo-url> SQLDocumentor && cd SQLDocumentor

# 3. Backend — creates backend/.venv, downloads Python 3.12+ if you have none
cd backend && uv sync && cd ..

# 4. Configure
cp sqldoc.example.yaml sqldoc.yaml        # connections -> databases -> schemas
cp .env.example .env                      # secrets referenced as "${VAR}" from sqldoc.yaml
open -e sqldoc.yaml                       # set host / port / databases / schemas

# 5. Check the connection, then scan
cd backend
uv run sqldoc --config ../sqldoc.yaml connections test local-aw
uv run sqldoc --config ../sqldoc.yaml scan
cd ..

# 6. Build the UI once, then serve API + UI on http://127.0.0.1:8000
cd frontend && npm ci && npm run build && cd ..
make serve                                # = cd backend && uv run sqldoc serve --open
```

`make` targets export `SQLDOC_CONFIG=<repo>/sqldoc.yaml` for you; when running
`uv run sqldoc ...` by hand from `backend/`, pass `--config ../sqldoc.yaml` or
`export SQLDOC_CONFIG=$PWD/../sqldoc.yaml` once per shell.

### Local SQL Server on macOS (optional)

SQL Server does not run natively on macOS; use Docker Desktop. The
`mcr.microsoft.com/mssql/server` image is amd64-only — on Apple Silicon enable
**Settings → General → Use Rosetta for x86_64/amd64 emulation** first.

```bash
docker run -d --name mssql -p 1433:1433 \
  -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='YourStrong!Passw0rd' \
  mcr.microsoft.com/mssql/server:2022-latest
```

Put the same password in `.env` as `MSSQL_SA_PASSWORD` and the example `local-aw`
connection works as-is. Sample databases (AdventureWorks, WideWorldImporters) are on
[Microsoft's sample-database page](https://learn.microsoft.com/sql/samples/adventureworks-install-configure);
restore the `.bak` with `sqlcmd` inside the container (`/opt/mssql-tools18/bin/sqlcmd`).

### Integrated (Kerberos) authentication on macOS

Windows-authenticated connections need `pyodbc` + Microsoft ODBC Driver 18 and a
Kerberos ticket:

```bash
brew tap microsoft/mssql-release
brew trust microsoft/mssql-release        # recent Homebrew requires trusting third-party taps first
brew install msodbcsql18                  # also installs unixodbc
cd backend && uv sync --extra odbc && cd ..

kinit you@CORP.EXAMPLE.COM                # obtain a ticket (check with klist)
cd backend && uv run sqldoc --config ../sqldoc.yaml connections test prod-dw
```

* In `sqldoc.yaml` use `auth: { mode: integrated }` and the server's **FQDN** as `host`
  (the name must match the SQL Server SPN, `MSSQLSvc/<fqdn>:<port>`).
* `driver: auto` switches to pyodbc automatically once the ODBC driver is registered;
  `connections test` prints which driver and auth scheme were negotiated.
* If `brew install msodbcsql18` fails with *"Xcode / Command Line Tools too outdated"*,
  update the Command Line Tools (Software Update, or `xcode-select --install` after
  removing the old ones) and retry — Homebrew builds `unixodbc` from source on newer
  macOS releases until a bottle exists.

## Setting up on Windows

Tested with Windows 11 x64 and PowerShell 7 (Windows PowerShell 5.1 also works).
`winget` ships with Windows 10 21H2+ / Windows 11.

```powershell
# 1. Tools — then close and reopen the terminal so PATH is refreshed
winget install --id astral-sh.uv -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Git.Git -e

# 2. Get the code
git clone <repo-url> SQLDocumentor; cd SQLDocumentor

# 3. Backend — creates backend\.venv, downloads Python 3.12+ if you have none
cd backend; uv sync; cd ..

# 4. Configure
Copy-Item sqldoc.example.yaml sqldoc.yaml
Copy-Item .env.example .env
notepad sqldoc.yaml                       # set host / port / databases / schemas
notepad .env                              # MSSQL_SA_PASSWORD=... (or your SQL login's password)

# 5. Check the connection, then scan
cd backend
uv run sqldoc --config ..\sqldoc.yaml connections test local-aw
uv run sqldoc --config ..\sqldoc.yaml scan
cd ..

# 6. Build the UI once, then serve API + UI on http://127.0.0.1:8000
cd frontend; npm ci; npm run build; cd ..
cd backend; uv run sqldoc --config ..\sqldoc.yaml serve --open
```

There is no `make` on Windows by default; the equivalents of the Makefile targets are:

| `make` target | PowerShell equivalent (from the repo root) |
|---|---|
| `make serve` | `cd backend; uv run sqldoc --config ..\sqldoc.yaml serve --open` |
| `make scan` | `cd backend; uv run sqldoc --config ..\sqldoc.yaml scan` |
| `make dev-api` | `cd backend; uv run uvicorn sqldoc.api.app:create_app --factory --reload --port 8000` |
| `make dev-web` | `cd frontend; npm run dev` |
| `make build` | `cd frontend; npm ci; npm run build` |
| `make test-unit` | `cd backend; uv run pytest tests/unit -q` |
| `make lint` | `cd backend; uv run ruff check src tests` then `cd frontend; npm run lint` |

To stop typing `--config`, set the variable once per session
(`$env:SQLDOC_CONFIG = "$PWD\sqldoc.yaml"`) or permanently
(`[Environment]::SetEnvironmentVariable("SQLDOC_CONFIG", "C:\path\to\sqldoc.yaml", "User")`).
The `dev-api` uvicorn command needs the same variable for the API to find the config.

### Windows authentication (SSPI) on Windows

Integrated auth uses the Windows account running `sqldoc` — no `kinit` needed — but it
requires `pyodbc` and Microsoft ODBC Driver 18:

```powershell
winget install --id Microsoft.msodbcsql.18 -e   # or the MSI from https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server
cd backend; uv sync --extra odbc
uv run sqldoc --config ..\sqldoc.yaml connections test prod-dw
```

Use `auth: { mode: integrated }` in `sqldoc.yaml`. On a domain-joined machine that is
all; to use domain credentials from a non-domain machine start the terminal with
`runas /netonly /user:DOMAIN\you powershell` and run `sqldoc` from it.

### Connecting to a local SQL Server on Windows

* **SQL Server Developer / Express installed locally:** `sqldoc` always connects over
  TCP (`tcp:<host>,<port>`), so enable **TCP/IP** in *SQL Server Configuration Manager →
  SQL Server Network Configuration → Protocols* and, for a named instance such as
  `.\SQLEXPRESS`, give it a fixed port under *TCP/IP → IP Addresses → IPAll → TCP Port*
  (e.g. `1433`), then restart the service. In `sqldoc.yaml` set `host: localhost` and that
  `port` — `host\INSTANCE` names and the SQL Browser service are not used.
* **Docker Desktop:** same `docker run` command as in the macOS section (no Rosetta step
  on x64).
* A local instance usually presents a self-signed certificate, so keep
  `trust_server_certificate: true` (the default in the example config).

### Windows notes

* Paths in `sqldoc.yaml` (e.g. `storage.sqlite_path`) are resolved relative to the
  config file and may use either `/` or `\`.
* `npm run dev:mock` uses POSIX `VAR=value` syntax; on Windows run
  `$env:VITE_MOCK_API = "1"; npm run dev` instead.
* The API and Vite bind to `127.0.0.1` by default, which needs no firewall rule; only
  `sqldoc serve --host 0.0.0.0` (to reach the UI from another machine) triggers the
  Windows Firewall prompt.

## Configuration (`sqldoc.yaml`)

```yaml
version: 1
storage: { sqlite_path: ./sqldoc.sqlite }        # relative to the config file
connections:
  - name: local-aw
    host: localhost
    port: 1433
    auth: { mode: sql, username: sa, password: "${MSSQL_SA_PASSWORD}" }
    driver: auto                # auto | pymssql | pyodbc
    encrypt: true
    trust_server_certificate: true
    databases:
      - { name: AdventureWorks2022, schemas: [Sales, HumanResources] }
  - name: prod-dw               # integrated auth (Kerberos on macOS/Linux via kinit, SSPI on Windows)
    host: sqlprod01.corp.example.com   # FQDN must match the SPN
    auth: { mode: integrated }
    databases:
      - { name: DW, schemas: [dbo] }
scan:
  cascade_foreign_keys: true
  include_triggers_of_cascaded_tables: true
  collect_stats: true
  parse_lineage: true
```

`${VAR}` references are resolved from the process environment, then from a `.env`
next to the config file. Quote them inside `{ }` flow mappings — bare braces are YAML
syntax. Secrets are never written to SQLite.

### Drivers

| Driver | Install | Auth | Notes |
|---|---|---|---|
| `pymssql` (default) | `uv sync` (bundled FreeTDS, no system packages) | SQL login | TLS negotiated best-effort; certificates not validated. |
| `pyodbc` | `uv sync --extra odbc` + Microsoft ODBC Driver 18 (macOS: `brew tap microsoft/mssql-release && brew install msodbcsql18`; Windows: `winget install Microsoft.msodbcsql.18`; Debian/Ubuntu: `apt install msodbcsql18`) | SQL login **and** integrated (Kerberos/SSPI) | Required for `auth.mode: integrated` and enforced TLS. |

`driver: auto` picks pyodbc when it and the Microsoft driver are installed, else pymssql.
`sqldoc connections test NAME` prints what the current machine can do.

### Permissions

Catalog extraction needs only read access plus `VIEW DEFINITION` (for module bodies and
lineage). Stats need `VIEW DATABASE STATE` (table/index stats) and `VIEW SERVER STATE`
(procedure stats, missing indexes); missing permissions become scan warnings, not
failures.

## CLI

```
sqldoc connections list | test NAME
sqldoc scan [--connection NAME]... [--no-stats] [--no-lineage]
sqldoc scans list | prune --keep N
sqldoc serve [--host H] [--port P] [--open]
sqldoc db upgrade
```

`--config` / `SQLDOC_CONFIG` selects the YAML file (default `./sqldoc.yaml`);
`--db` / `SQLDOC_DB` overrides the SQLite path.

## How lineage works

1. **Object level (authoritative):** `sys.sql_expression_dependencies`, foreign keys,
   trigger→table and synonym links from the catalog. Ambiguous rows (XML / hierarchyid
   method calls) are recorded but never create nodes; cross-database references cascade
   only into databases configured on the same connection, otherwise they become
   `external` nodes.
2. **Column level (best effort):** every view, function, procedure and trigger body is
   split into statements (T-SQL rarely has semicolons), writes are rewritten into SELECT
   projections, and `sqlglot` resolves each output column to the base columns it reads.
   Each edge carries a confidence — `exact` (pure column pass-through), `inferred`
   (expression / aggregate / unknown column / temp table), `unresolved` (`SELECT *` from
   an unknown table, `INSERT ... EXEC`, dynamic SQL). Temp tables and table variables
   appear as pseudo objects; procedure result sets appear as pseudo columns.
3. Anything the parser cannot handle (full-text predicates, `OUTPUT ... INTO`, dynamic
   SQL) is recorded per statement in `lineage_issues`; the object keeps its catalog edges.

## Development

Run the API and the Vite dev server separately; Vite proxies `/api` to `:8000`.

```bash
make dev-api            # FastAPI with reload on :8000 (reads sqldoc.yaml at the repo root)
make dev-web            # Vite on :5173
make test-unit          # backend unit tests
make test-integration   # needs the AdventureWorks container on localhost:1433 + MSSQL_SA_PASSWORD
make lint               # ruff + oxlint
make api-types          # regenerate frontend/src/api/schema.d.ts from the running API
```

The `Makefile` assumes macOS/Linux; Windows users run the commands from the table in
[Setting up on Windows](#setting-up-on-windows). `cd frontend && npm test` runs the
vitest suite, `npm run e2e` the Playwright smoke test against a running backend.
