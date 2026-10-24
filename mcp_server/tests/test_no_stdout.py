import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_no_print_calls_in_package():
    offenders = []
    for f in (ROOT / "kawach_mcp").rglob("*.py"):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<![\w.])print\(", line):
                offenders.append(f"{f.name}:{n}")
    assert not offenders, offenders


def test_stdout_is_pure_jsonrpc():
    """Spawn the server like a real client: keep stdin open until both answers arrive, then close it."""
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"},
    ]
    env = {**os.environ, "KAWACH_BASE_URL": "http://127.0.0.1:9", "KAWACH_LOG_LEVEL": "DEBUG", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-m", "kawach_mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env, cwd=ROOT)
    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.extend(iter(proc.stdout.readline, "")), daemon=True)
    reader.start()
    try:
        for m in msgs:
            proc.stdin.write(json.dumps(m) + "\n")
            proc.stdin.flush()
        deadline = time.time() + 40
        while time.time() < deadline and sum(1 for ln in lines if ln.strip()) < 3:
            time.sleep(0.1)
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    reader.join(timeout=5)
    stderr = proc.stderr.read()
    out = [ln for ln in lines if ln.strip()]
    assert out, f"no stdout. stderr: {stderr[-500:]}"
    parsed = [json.loads(ln) for ln in out]  # raises if any byte of stdout is not JSON
    assert all(p.get("jsonrpc") == "2.0" for p in parsed)
    by_id = {p.get("id"): p for p in parsed}
    assert by_id[1]["result"]["serverInfo"]["name"] == "kawach-qa"
    assert len(by_id[2]["result"]["tools"]) >= 50
    assert len(by_id[3]["result"]["prompts"]) == 5
    assert "health probe: unreachable" in stderr  # the startup probe ran, logged to stderr only, and did not block
