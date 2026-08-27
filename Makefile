# Config lives at the repo root; backend commands run from backend/, so pass it explicitly.
CONFIG ?= $(CURDIR)/sqldoc.yaml
export SQLDOC_CONFIG := $(CONFIG)

.PHONY: dev-api dev-web build test test-unit test-integration api-types lint scan serve

dev-api:            ## FastAPI with reload on :8000
	cd backend && uv run uvicorn sqldoc.api.app:create_app --factory --reload --port 8000

dev-web:            ## Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

build:              ## Production SPA build into frontend/dist
	cd frontend && npm ci && npm run build

test: test-unit     ## Unit tests (backend + frontend)
	cd frontend && npm test -- --run

test-unit:
	cd backend && uv run pytest tests/unit -q

test-integration:   ## Needs the mssql container + MSSQL_SA_PASSWORD (or SQLDOC_TEST_PASSWORD)
	cd backend && uv run pytest -m integration -q

api-types:          ## Regenerate frontend/src/api/schema.d.ts from the running API
	cd frontend && npm run api:types

lint:
	cd backend && uv run ruff check src tests
	cd frontend && npm run lint

scan:               ## Run a scan for every configured connection
	cd backend && uv run sqldoc scan

serve:              ## Serve API + built SPA on :8000
	cd backend && uv run sqldoc serve --open
