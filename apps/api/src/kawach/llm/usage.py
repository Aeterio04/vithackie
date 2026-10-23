"""Thread-safe LLM usage and cost tracking per run."""

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Optional

from kawach.core.config import settings
from kawach.schemas.metrics import LlmUsage
from kawach.storage.artifacts import run_dir

_usage_lock = threading.RLock()


def record_usage(
    run_id: Optional[str],
    input_tokens: int,
    output_tokens: int,
    is_cache_hit: bool,
) -> None:
    """Record LLM token consumption and costs to run's llm_usage.json."""
    if not run_id:
        return

    with _usage_lock:
        usage_file = run_dir(run_id) / "llm_usage.json"
        cur_usage = {
            "calls": 0,
            "cacheHits": 0,
            "inputTokens": 0,
            "outputTokens": 0,
            "costUsd": 0.0,
        }

        if usage_file.exists():
            try:
                with open(usage_file, "r", encoding="utf-8") as f:
                    cur_usage = json.load(f)
            except Exception:
                pass

        cur_usage["calls"] += 1
        if is_cache_hit:
            cur_usage["cacheHits"] += 1

        cur_usage["inputTokens"] += input_tokens
        cur_usage["outputTokens"] += output_tokens

        cost = (input_tokens * settings.LLM_PRICE_IN_PER_MTOK / 1e6) + (
            output_tokens * settings.LLM_PRICE_OUT_PER_MTOK / 1e6
        )
        cur_usage["costUsd"] = round(cur_usage.get("costUsd", 0.0) + cost, 6)

        # Atomic write with Windows retry
        temp_file = usage_file.with_suffix(f".tmp.{secrets.token_hex(4)}")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(cur_usage, f, indent=2)
                f.flush()
                import os
                os.fsync(f.fileno())

            replaced = False
            for attempt in range(8):
                try:
                    os.replace(temp_file, usage_file)
                    replaced = True
                    break
                except (PermissionError, OSError):
                    time.sleep(0.03 * (attempt + 1))
            if not replaced:
                try:
                    with open(usage_file, "w", encoding="utf-8") as f:
                        json.dump(cur_usage, f, indent=2)
                except Exception:
                    pass
                try:
                    if temp_file.exists():
                        temp_file.unlink()
                except Exception:
                    pass
        except Exception:
            pass


def usage(run_id: str) -> LlmUsage:
    """Return token usage and estimated cost for a run, or zeros if missing."""
    usage_file = run_dir(run_id) / "llm_usage.json"
    if not usage_file.exists():
        return LlmUsage()
    try:
        with open(usage_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return LlmUsage(**data)
    except Exception:
        return LlmUsage()
