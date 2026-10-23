"""Export OpenAPI 3.1.0 schema to packages/contracts/openapi.json."""

import json
from pathlib import Path
from kawach.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FILE = REPO_ROOT / "packages" / "contracts" / "openapi.json"


def export_openapi() -> None:
    app = create_app()
    openapi_data = app.openapi()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(openapi_data, f, indent=2, ensure_ascii=False)
    print(f"Exported OpenAPI schema to {OUTPUT_FILE} ({len(openapi_data.get('paths', {}))} paths)")


if __name__ == "__main__":
    export_openapi()
