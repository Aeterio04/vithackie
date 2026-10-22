"""LLM disk cache helpers."""

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional, Tuple

from kawach.core.config import settings


def compute_cache_key(
    *,
    provider: str,
    model: str,
    system: str,
    prompt: str,
    schema_name: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Compute deterministic SHA256 cache key from request parameters."""
    payload = {
        "max_tokens": max_tokens,
        "model": model,
        "prompt": prompt,
        "provider": provider,
        "schema_name": schema_name,
        "system": system,
        "temperature": temperature,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_cache(cache_dir: Path, key: str) -> Optional[Tuple[str, int, int]]:
    """Check cache directory for key. Returns (text, in_tokens, out_tokens) or None."""
    if settings.LLM_CACHE not in ("on", "readonly"):
        return None
    cache_file = cache_dir / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data["text"], data.get("inputTokens", 0), data.get("outputTokens", 0))
    except Exception:
        return None


def write_cache(cache_dir: Path, key: str, text: str, input_tokens: int, output_tokens: int) -> None:
    """Write response to disk cache atomically with Windows retry."""
    if settings.LLM_CACHE != "on":
        return
    cache_file = cache_dir / f"{key}.json"
    temp_file = cache_file.with_suffix(f".tmp.{secrets.token_hex(4)}")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "text": text,
                    "inputTokens": input_tokens,
                    "outputTokens": output_tokens,
                },
                f,
                ensure_ascii=False,
            )
            f.flush()
            os.fsync(f.fileno())

        replaced = False
        for attempt in range(8):
            try:
                os.replace(temp_file, cache_file)
                replaced = True
                break
            except (PermissionError, OSError):
                time.sleep(0.03 * (attempt + 1))
        if not replaced:
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "text": text,
                            "inputTokens": input_tokens,
                            "outputTokens": output_tokens,
                        },
                        f,
                        ensure_ascii=False,
                    )
            except Exception:
                pass
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
