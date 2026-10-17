"""Explorer agent that coordinates Playwright crawl and LLM app map summarization.

Implemented by Track B.
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.llm import get_llm
from app.models import AppMap, Feature, RunInput
from app import prompts
from app import storage


def run_explorer(run_id: str) -> AppMap:
    """Crawl the target web application and generate a complete AppMap."""
    # 1. Load run configuration and input
    run_input = storage.load_model(run_id, "input.json", RunInput)
    base_url = run_input.targetUrl if run_input else "http://localhost:4000"
    username = run_input.username if run_input else ""
    password = storage.read_secret_password(run_id)
    background_prompt = run_input.prompt if run_input and run_input.prompt else "Web application under test."

    max_pages = run_input.budgets.maxPages if (run_input and run_input.budgets) else settings.MAX_PAGES
    explore_seconds = run_input.budgets.exploreSeconds if (run_input and run_input.budgets) else settings.EXPLORE_SECONDS

    # Set stage to exploring
    storage.set_stage(run_id, "exploring", step="Starting browser", done=0, total=max_pages)

    out_file = (storage.run_dir(run_id) / "explore_raw.json").resolve()

    # 2. Setup environment for runner/explore.ts
    runner_dir = (settings.repo_root / "runner").resolve()
    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["TEST_USERNAME"] = username
    env["TEST_PASSWORD"] = password
    env["MAX_PAGES"] = str(max_pages)
    env["EXPLORE_SECONDS"] = str(explore_seconds)
    env["ALLOWED_HOSTS"] = ",".join(settings.ALLOWED_HOSTS)
    env["OUT_FILE"] = str(out_file)

    # 3. Spawn crawler subprocess
    # Use npx tsx explore.ts
    cmd = ["npx", "tsx", "explore.ts"]
    if os.name == "nt":
        # On Windows, npx is a cmd script
        cmd = ["cmd", "/c", "npx", "tsx", "explore.ts"]

    stderr_chunks: List[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(runner_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        timeout_seconds = explore_seconds + 60
        start_wait = time.time()

        # Read stdout line by line to stream progress updates
        page_pattern = re.compile(r"^PAGE\s+(\d+)/(\d+)\s+(.*)$")

        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                line_str = line.strip()
                if not line_str:
                    continue

                match = page_pattern.match(line_str)
                if match:
                    done_n = int(match.group(1))
                    total_n = int(match.group(2))
                    page_path = match.group(3)
                    storage.set_stage(
                        run_id,
                        "exploring",
                        step=f"Crawling {page_path}",
                        done=done_n,
                        total=total_n,
                    )

                if time.time() - start_wait > timeout_seconds:
                    proc.kill()
                    break

        _, stderr_text = proc.communicate(timeout=10)
        if stderr_text:
            stderr_chunks.append(stderr_text)

    except Exception as crawl_err:
        stderr_chunks.append(f"Subprocess execution error: {crawl_err}")

    # 4. Load raw crawler output
    raw_data = storage.read_json(run_id, "explore_raw.json")
    if not raw_data or not isinstance(raw_data, dict):
        err_tail = "".join(stderr_chunks)[-500:] if stderr_chunks else "No output file produced."
        raw_data = {
            "baseUrl": base_url,
            "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "login": {"attempted": False, "success": False, "url": None, "note": None},
            "pages": [],
            "summary": "(summary unavailable)",
            "features": [],
            "stats": {"pagesVisited": 0, "durationSeconds": 0.0, "budgetHit": None},
            "error": f"Explorer produced no output: {err_tail}",
        }

    # 5. LLM Summarization Step
    storage.set_stage(run_id, "exploring", step="Synthesizing app map summary", done=max_pages, total=max_pages)

    compact_pages = []
    for p in raw_data.get("pages", []):
        compact_pages.append({
            "path": p.get("path"),
            "title": p.get("title"),
            "requiresAuth": p.get("requiresAuth", False),
            "headings": [h.get("text") for h in p.get("headings", [])[:5]],
            "forms": [
                {
                    "id": f.get("id"),
                    "method": f.get("method"),
                    "fields": [
                        {
                            "label": fld.get("label"),
                            "type": fld.get("type"),
                            "role": fld.get("role"),
                        }
                        for fld in f.get("fields", [])
                    ],
                }
                for f in p.get("forms", [])
            ],
            "buttons": [b.get("text") for b in p.get("buttons", [])[:8]],
            "consoleErrorCount": len(p.get("consoleErrors", [])),
        })

    compact_str = json.dumps(compact_pages, ensure_ascii=False)[:12000]

    try:
        prompt_text = prompts.load_prompt(
            "explore_summary",
            guard=prompts.guard(),
            prompt=background_prompt,
            app_map=prompts.untrusted(compact_str, "app_map"),
        )
        llm = get_llm()
        summary_resp = llm.complete_json(
            system="You are an expert QA and software architect analysing web application crawler results.",
            prompt=prompt_text,
            schema_name="explore_summary",
            run_id=run_id,
        )
        if isinstance(summary_resp, dict):
            summary = summary_resp.get("summary", "")
            features_raw = summary_resp.get("features", [])
        else:
            summary = "(summary unavailable)"
            features_raw = []
    except Exception as llm_err:
        summary = "(summary unavailable)"
        features_raw = []

    # 6. Assemble AppMap
    raw_data["summary"] = summary
    raw_data["features"] = features_raw
    raw_data["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    app_map = AppMap.model_validate(raw_data)
    storage.save_model(run_id, "app_map.json", app_map)

    return app_map
