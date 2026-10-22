# Autonomous AI QA Engineer

An autonomous AI QA engineering pipeline that explores web applications, plans test catalogs linked to specs, writes Playwright test scripts, executes tests, triages assertion failures into bug candidates, and proves defects with 3x deterministic replays.

## Ports
- **Target App**: `http://localhost:4000` (`examples/target-app`)
- **Backend API**: `http://localhost:8000` (`apps/api`)
- **Frontend UI**: `http://localhost:3000` (`apps/web`)

## Monorepo Layout
- `apps/api/`: FastAPI backend and LangGraph multi-agent orchestrator
- `apps/web/`: Next.js web dashboard
- `apps/runner/`: Playwright test runner and crawler harness
- `packages/contracts/`: Shared schemas, samples, types, and openapi spec
- `examples/target-app/`: Benchmark target application
- `benchmarks/planted-bugs/`: Ground truth bug definitions
- `data/`: Local artifacts and runs (git-ignored)
- `demo-data/`: Tracked golden demo runs and benchmark fixtures

## Quickstart
- `make setup`: Create python virtualenv, install backend requirements, runner dependencies, web dependencies & Playwright chromium.
- `make target`: Start the demo target app on port 4000.
- `make backend`: Start the FastAPI backend server on port 8000.
- `make frontend`: Start the Next.js frontend application on port 3000.
- `make test`: Run backend test suite.
- `make validate-contracts`: Validate all contract samples against Pydantic models.
- `make schemas`: Export JSON Schemas for all models to `packages/contracts/schemas/`.
- `make types`: Regenerate TypeScript contract types from OpenAPI schema.

