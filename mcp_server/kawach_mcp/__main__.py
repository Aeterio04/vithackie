"""Entry point: python -m kawach_mcp [--transport stdio|streamable-http] [--port N] [--check]."""

import argparse
import asyncio
import logging
import sys

from . import __version__


def _configure_logging(level: str) -> None:
    for stream in (sys.stderr, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level, logging.INFO))
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _check() -> int:
    """Health probe + auth check with a human-readable report. Exit code 0 = ready, 1 = problem."""
    from .client import get_client
    from .config import get_settings
    from .tools.system import health_check, whoami

    out = sys.stdout.write  # --check exits before serving, so writing to stdout is fine here
    s = get_settings()
    lines = [
        f"kawach-mcp {__version__}",
        f"  backend URL : {s.base_url}",
        f"  auth mode   : {s.auth_mode}",
        f"  account     : {s.email or '(none configured)'}",
        f"  download dir: {s.download_dir}",
    ]
    code = 0
    h = await health_check()
    if h["status"] == "unreachable":
        lines += [f"  backend     : UNREACHABLE ({h.get('message')})",
                  "RESULT: NOT READY. Start the KAWACH backend, then run --check again."]
        out("\n".join(lines) + "\n")
        await get_client().aclose()
        return 1
    lines.append(f"  backend     : OK ({h['status']}, workers up: {h.get('workers_up')}, queue: {h.get('queue_depth')})")
    try:
        w = await whoami()
        if w["authenticated"]:
            lines.append(f"  login       : OK, acting as {w['email']}")
        else:
            lines.append(f"  login       : FAILED. {w.get('note')}")
            code = 1
    except Exception as e:  # report, do not crash
        lines.append(f"  login       : FAILED. {e}")
        code = 1
    lines.append("RESULT: READY." if code == 0 else "RESULT: NOT READY (authentication).")
    out("\n".join(lines) + "\n")
    await get_client().aclose()
    return code


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="kawach-mcp", description="KAWACH MCP server")
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    ap.add_argument("--port", type=int, default=8765, help="port for streamable-http")
    ap.add_argument("--check", action="store_true", help="test config, backend connectivity and login, then exit")
    args = ap.parse_args(argv)

    from .config import get_settings

    _configure_logging(get_settings().log_level)
    if args.check:
        raise SystemExit(asyncio.run(_check()))

    from .server import create_server

    create_server(port=args.port).run(transport=args.transport)


if __name__ == "__main__":
    main()
