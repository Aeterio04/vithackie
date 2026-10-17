# Autonomous AI QA Engineer

An autonomous AI QA engineering pipeline that explores web applications, plans test catalogs linked to specs, writes Playwright test scripts, executes tests, triages assertion failures into bug candidates, and proves defects with 3x deterministic replays.

## Ports
- **Target App**: `http://localhost:4000`
- **Backend API**: `http://localhost:8000`
- **Frontend UI**: `http://localhost:5173`

## Quickstart
- `make setup`: Create python virtualenv, install backend requirements, install runner & Playwright chromium.
- `make target`: Start the demo target app with 9 planted bugs on port 4000.
- `make backend`: Start the FastAPI backend server on port 8000.
- `make frontend`: Start the frontend application.
- `make validate-contracts`: Validate all contract samples against Pydantic models.
- `make schemas`: Export JSON Schemas for all models to `contracts/schemas/`.
