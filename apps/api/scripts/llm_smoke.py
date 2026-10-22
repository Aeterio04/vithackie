"""Smoke test for LLM provider configuration and caching.

Run with: python backend/scripts/llm_smoke.py
"""

import sys
import os
from pathlib import Path

# Ensure repo root and backend/ are on python path
repo_root = Path(__file__).resolve().parent.parent.parent
backend_dir = repo_root / "backend"
sys.path.insert(0, str(backend_dir))

from app.config import settings
from app.llm import get_llm, LLMError, usage
from app.storage import new_run_id

def main():
    print(f"=== LLM SMOKE TEST ===")
    print(f"Provider: {settings.LLM_PROVIDER}")
    print(f"Model:    {settings.LLM_MODEL}")
    print(f"Cache:    {settings.LLM_CACHE}")
    print("-" * 30)

    llm = get_llm()
    test_run_id = new_run_id()

    system_prompt = "You are a concise QA engineering system assistant."
    user_prompt = 'Return ONLY this JSON object: {"ok": true, "model": "report your model name"}'

    try:
        print("\n[Call 1] Calling provider...")
        res1 = llm.complete_json(
            system=system_prompt,
            prompt=user_prompt,
            schema_name="_example",
            run_id=test_run_id,
        )
        print("Response 1:", res1)
        u1 = usage(test_run_id)
        print(f"Usage after Call 1: calls={u1.calls}, cacheHits={u1.cacheHits}, inTok={u1.inputTokens}, outTok={u1.outputTokens}, costUsd=${u1.costUsd:.6f}")

        print("\n[Call 2] Calling again with identical prompt (checking cache)...")
        res2 = llm.complete_json(
            system=system_prompt,
            prompt=user_prompt,
            schema_name="_example",
            run_id=test_run_id,
        )
        print("Response 2:", res2)
        u2 = usage(test_run_id)
        print(f"Usage after Call 2: calls={u2.calls}, cacheHits={u2.cacheHits}, inTok={u2.inputTokens}, outTok={u2.outputTokens}, costUsd=${u2.costUsd:.6f}")

        if settings.LLM_CACHE in ("on", "readonly") and settings.LLM_PROVIDER != "fake":
            if u2.cacheHits > u1.cacheHits:
                print("\n[SUCCESS] Cache hit verified!")
            else:
                print("\n[WARNING] Cache did not hit on second identical call.")
        else:
            print("\n[NOTE] Provider is 'fake' or cache is off; cache hits are not expected.")

        print("\nAll checks passed.")

    except LLMError as e:
        print(f"\n[ERROR] LLM Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
