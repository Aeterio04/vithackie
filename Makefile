.PHONY: setup target backend frontend validate-contracts schemas test demo

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

ifeq ($(OS),Windows_NT)
    VENV_BIN := $(ROOT_DIR)/.venv/Scripts
    VENV_PY := $(ROOT_DIR)/.venv/Scripts/python.exe
    VENV_UVICORN := $(ROOT_DIR)/.venv/Scripts/uvicorn.exe
    NPM := npm.cmd
    NPX := npx.cmd
else
    VENV_BIN := $(ROOT_DIR)/.venv/bin
    VENV_PY := $(ROOT_DIR)/.venv/bin/python
    VENV_UVICORN := $(ROOT_DIR)/.venv/bin/uvicorn
    NPM := npm
    NPX := npx
endif

setup:
	python -m venv .venv
	@if exist .venv\Scripts\pip.exe ( .venv\Scripts\pip install -r apps/api/requirements.txt ) else ( .venv/bin/pip install -r apps/api/requirements.txt )
	cd apps/runner && $(NPM) install && $(NPX) playwright install chromium
	cd apps/web && $(NPM) install

target:
	@if exist examples\target-app\package.json ( cd examples/target-app && $(NPM) start ) else if [ -f examples/target-app/package.json ]; then ( cd examples/target-app && $(NPM) start ); else echo "target-app not found"; fi

backend:
	@if exist apps\api\app\main.py ( cd apps/api && $(VENV_UVICORN) app.main:app --reload --port 8000 ) else if [ -f apps/api/app/main.py ]; then ( cd apps/api && $(VENV_UVICORN) app.main:app --reload --port 8000 ); else echo "apps/api app.main not found"; fi

frontend:
	@if exist apps\web\package.json ( cd apps/web && $(NPM) run dev ) else if [ -f apps/web/package.json ]; then ( cd apps/web && $(NPM) run dev ); else echo "apps/web not found"; fi

validate-contracts:
	cd apps/api && ( $(VENV_PY) scripts/validate_samples.py || python scripts/validate_samples.py )

schemas:
	cd apps/api && ( $(VENV_PY) scripts/export_schemas.py || python scripts/export_schemas.py )

types:
	$(NPX) -y openapi-typescript packages/contracts/openapi.json -o packages/contracts/types.ts
	$(NPX) -y openapi-typescript packages/contracts/openapi.json -o apps/web/src/generated/api-types.ts

test:
	cd $(ROOT_DIR) && $(VENV_PY) -m pytest apps/api/tests/ -v

demo:
	@echo not built yet

