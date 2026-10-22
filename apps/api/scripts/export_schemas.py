"""Export JSON Schema for each Pydantic model to contracts/schemas/<ModelName>.schema.json."""

import inspect
import json
import sys
from pathlib import Path
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.models as models_module

SCHEMAS_DIR = REPO_ROOT / "contracts" / "schemas"
SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)


def export_all_schemas() -> None:
    exported_count = 0
    for name, obj in inspect.getmembers(models_module):
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj is not BaseModel:
            schema_data = obj.model_json_schema()
            output_file = SCHEMAS_DIR / f"{name}.schema.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(schema_data, f, indent=2, ensure_ascii=False)
            exported_count += 1

    print(f"Successfully exported {exported_count} schemas to contracts/schemas/")


if __name__ == "__main__":
    export_all_schemas()
