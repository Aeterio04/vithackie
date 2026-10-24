"""Generate docs/TOOL_REFERENCE.md from the LIVE server schema (tools, prompts, resources).

    .venv/Scripts/python scripts/gen_tool_reference.py
"""

import asyncio
import sys
from pathlib import Path

from kawach_mcp import __version__
from kawach_mcp.server import SERVER_NAME, create_server

OUT = Path(__file__).resolve().parent.parent / "docs" / "TOOL_REFERENCE.md"


def _type(schema: dict) -> str:
    if "anyOf" in schema:
        parts = [_type(x) for x in schema["anyOf"] if x.get("type") != "null"]
        return " | ".join(parts) or "any"
    t = schema.get("type", "any")
    if t == "array":
        return f"list[{_type(schema.get('items', {}))}]"
    return t


def _cell(text: str) -> str:
    return " ".join((text or "").split()).replace("|", "\\|")


async def build() -> str:
    server = create_server()
    tools = sorted(await server.list_tools(), key=lambda t: t.name)
    prompts = sorted(await server.list_prompts(), key=lambda p: p.name)
    templates = await server.list_resource_templates()
    resources = await server.list_resources()
    L = [f"# {SERVER_NAME} tool reference", "",
         f"Generated from the live server schema by `scripts/gen_tool_reference.py` (kawach-mcp {__version__}). "
         f"{len(tools)} tools, {len(prompts)} prompts, {len(resources) + len(templates)} resources. Do not edit by hand.", ""]
    L += ["## Tools", ""]
    for t in tools:
        a = t.annotations
        flags = []
        if a and a.readOnlyHint:
            flags.append("read-only")
        if a and a.destructiveHint:
            flags.append("DESTRUCTIVE (needs confirm=true)")
        if a and a.idempotentHint:
            flags.append("idempotent")
        L += [f"### `{t.name}`" + (f"  ({', '.join(flags)})" if flags else ""), "", (t.description or "").strip(), ""]
        props = t.inputSchema.get("properties", {})
        required = set(t.inputSchema.get("required", []))
        if props:
            L += ["| Parameter | Type | Required | Default | Description |", "|---|---|---|---|---|"]
            for name, sch in props.items():
                default = "" if name in required else f"`{sch.get('default')!r}`"
                L.append(f"| `{name}` | {_type(sch)} | {'yes' if name in required else 'no'} | {default} | {_cell(sch.get('description', ''))} |")
            L.append("")
        else:
            L += ["_No parameters._", ""]
    L += ["## Prompts", ""]
    for p in prompts:
        args = ", ".join(f"{x.name}{'' if x.required else '?'}" for x in (p.arguments or []))
        L.append(f"- **`{p.name}`**({args}): {p.description}")
    L += ["", "## Resources", ""]
    for r in resources:
        L.append(f"- `{r.uri}`: {r.description}")
    for r in templates:
        L.append(f"- `{r.uriTemplate}`: {r.description}")
    return "\n".join(L) + "\n"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(asyncio.run(build()), encoding="utf-8")
    sys.stderr.write(f"wrote {OUT}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
