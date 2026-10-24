"""Write antigravity_mcp_config.json: a ready-to-paste Antigravity MCP block using THIS machine's absolute paths.

    .venv/Scripts/python scripts/gen_antigravity_config.py [--email you@example.com] [--base-url http://localhost:8000]

The password is never written: it is always the placeholder below (edit it in Antigravity's raw config, not here).
Paths use forward slashes so the JSON stays valid on Windows.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "antigravity_mcp_config.json"


def build(email: str, base_url: str) -> dict:
    return {
        "mcpServers": {
            "kawach": {
                "command": Path(sys.executable).resolve().as_posix(),
                "args": ["-m", "kawach_mcp"],
                "env": {
                    "KAWACH_BASE_URL": base_url,
                    "KAWACH_EMAIL": email,
                    "KAWACH_PASSWORD": "<your-kawach-password>",
                    "KAWACH_DOWNLOAD_DIR": (ROOT / "kawach_downloads").resolve().as_posix(),
                },
            }
        }
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="<your-kawach-email>")
    ap.add_argument("--base-url", default="http://localhost:8000")
    args = ap.parse_args()
    cfg = build(args.email, args.base_url)
    OUT.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    json.loads(OUT.read_text(encoding="utf-8"))  # must be valid JSON
    sys.stderr.write(f"wrote {OUT}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
