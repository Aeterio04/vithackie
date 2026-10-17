.PHONY: setup target backend frontend validate-contracts schemas demo

ifeq ($(OS),Windows_NT)
    VENV_BIN := ../.venv/Scripts
    VENV_PY := ../.venv/Scripts/python.exe
    VENV_UVICORN := ../.venv/Scripts/uvicorn.exe
    NPM := npm.cmd
    NPX := npx.cmd
else
    VENV_BIN := ../.venv/bin
    VENV_PY := ../.venv/bin/python
    VENV_UVICORN := ../.venv/bin/uvicorn
    NPM := npm
    NPX := npx
endif

setup:
	python -m venv .venv
	@if exist .venv\Scripts\pip.exe ( .venv\Scripts\pip install -r backend/requirements.txt ) else ( .venv/bin/pip install -r backend/requirements.txt )
	cd runner && $(NPM) install && $(NPX) playwright install chromium

target:
	@if exist target-app\package.json ( cd target-app && $(NPM) start ) else if [ -f target-app/package.json ]; then ( cd target-app && $(NPM) start ); else echo "target-app not built yet"; fi

backend:
	@if exist backend\app\main.py ( cd backend && $(VENV_UVICORN) app.main:app --reload --port 8000 ) else if [ -f backend/app/main.py ]; then ( cd backend && $(VENV_UVICORN) app.main:app --reload --port 8000 ); else echo "backend app.main not built yet"; fi

frontend:
	@if exist frontend\package.json ( cd frontend && $(NPM) run dev ) else if [ -f frontend/package.json ]; then ( cd frontend && $(NPM) run dev ); else echo "frontend not built yet"; fi

validate-contracts:
	cd backend && ( $(VENV_PY) scripts/validate_samples.py || python scripts/validate_samples.py )

schemas:
	cd backend && ( $(VENV_PY) scripts/export_schemas.py || python scripts/export_schemas.py )

demo:
	@echo not built yet
