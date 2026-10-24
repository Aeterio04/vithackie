"""Protocol-level proof: connect to the server exactly as Antigravity would and show RAW tool results.

Spawns the server using the command/args/env from antigravity_mcp_config.json (placeholders for email/password are
replaced from KAWACH_EMAIL / KAWACH_PASSWORD, which are never printed), then:
list_tools, list_prompts, list_resources, health_check, a deliberately failing call, get_run_summary on a real run,
and list_tools again to prove the server survived the error.

    KAWACH_EMAIL=.. KAWACH_PASSWORD=.. python scripts/protocol_proof.py [--run-id RUN_ID]
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONFIG = Path(__file__).resolve().parent.parent / "antigravity_mcp_config.json"


def raw(result) -> str:
    return "\n".join(getattr(c, "text", str(c)) for c in result.content)


def show(title: str, text: str, limit: int = 2500) -> None:
    print(f"\n----- {title}")
    print(text if len(text) <= limit else text[:limit] + f"\n... [{len(text) - limit} more chars]")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))["mcpServers"]["kawach"]
    env = dict(cfg["env"])
    env["KAWACH_EMAIL"] = os.environ["KAWACH_EMAIL"]
    env["KAWACH_PASSWORD"] = os.environ["KAWACH_PASSWORD"]
    env["KAWACH_BASE_URL"] = os.environ.get("KAWACH_BASE_URL", env["KAWACH_BASE_URL"])
    full_env = {**{k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH")}, **env}
    print(f"spawning: {cfg['command']} {' '.join(cfg['args'])}   (config: {CONFIG.name})")
    params = StdioServerParameters(command=cfg["command"], args=cfg["args"], env=full_env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print(f"initialize -> server '{init.serverInfo.name}' version {init.serverInfo.version}; instructions: {len(init.instructions or '')} chars")
            tools = (await s.list_tools()).tools
            prompts = (await s.list_prompts()).prompts
            resources = (await s.list_resources()).resources
            templates = (await s.list_resource_templates()).resourceTemplates
            print(f"list_tools     -> {len(tools)} tools")
            print(f"list_prompts   -> {len(prompts)} prompts: {', '.join(p.name for p in prompts)}")
            print(f"list_resources -> {len(resources)} resources + {len(templates)} templates: "
                  f"{', '.join(str(x.uri) for x in resources)}; {', '.join(t.uriTemplate for t in templates)}")
            show("health_check (raw tool result)", raw(await s.call_tool("health_check", {})))
            show("whoami (raw)", raw(await s.call_tool("whoami", {})))
            bad = await s.call_tool("get_run", {"run_id": "does-not-exist"})
            show(f"deliberate failure: get_run('does-not-exist')  isError={bad.isError}", raw(bad))
            again = await s.list_tools()
            print(f"\nserver still alive after the error: list_tools -> {len(again.tools)} tools")
            run_id = args.run_id
            if not run_id:
                runs = json.loads(raw(await s.call_tool("list_runs", {"limit": 1})))["runs"]
                run_id = runs[0]["run_id"] if runs else None
            if run_id:
                show(f"get_run_summary('{run_id}') (raw tool result)", raw(await s.call_tool("get_run_summary", {"run_id": run_id})), 4000)
                p = await s.get_prompt("explain_run", {"run_id": run_id})
                show("get_prompt('explain_run') (first 600 chars)", p.messages[0].content.text, 600)
            else:
                print("\n(no run exists for this account, so get_run_summary was NOT RUN)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
