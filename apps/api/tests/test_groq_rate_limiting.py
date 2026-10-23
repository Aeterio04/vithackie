"""Unit tests for Groq provider handler, rate limit manager, and schema token budgeting."""

from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
import time

from kawach.core.config import settings
from kawach.llm.client import LLM, LLMError
from kawach.llm.groq_handler import (
    SCHEMA_TOKEN_BUDGETS,
    GroqHandler,
    GroqRateLimiter,
    get_budgeted_max_tokens,
    parse_429_error,
)
from kawach.llm.usage import usage


def test_schema_token_budgets():
    """Verify all critical schemas have strict calibrated token budgets."""
    assert SCHEMA_TOKEN_BUDGETS["explore_summary"] <= 600
    assert SCHEMA_TOKEN_BUDGETS["planner"] <= 1500
    assert SCHEMA_TOKEN_BUDGETS["planner_single"] <= 800
    assert SCHEMA_TOKEN_BUDGETS["script_writer"] <= 900
    assert SCHEMA_TOKEN_BUDGETS["bug_reporter"] <= 800
    assert SCHEMA_TOKEN_BUDGETS["reviewer"] <= 600
    assert SCHEMA_TOKEN_BUDGETS["self_healing"] <= 750
    assert SCHEMA_TOKEN_BUDGETS["text"] <= 1000

    # Test get_budgeted_max_tokens
    # When requesting 4000 for planner, it clamps to 1500
    assert get_budgeted_max_tokens("planner", 4000) == 1500
    # When requesting smaller (e.g. 500), it honors the smaller value
    assert get_budgeted_max_tokens("planner", 500) == 500
    # Unknown schema defaults to 1000
    assert get_budgeted_max_tokens("unknown_schema_xyz", 2500) == 1000


def test_proactive_min_interval_pacing():
    """Verify limiter enforces anti-burst minimum interval between requests."""
    limiter = GroqRateLimiter(rpm_limit=100, tpm_limit=50000, min_interval=0.1, window_seconds=60.0)

    t0 = time.time()
    _, wait1 = limiter.acquire(est_prompt_tokens=100, max_tokens=200)
    assert wait1 == 0.0

    _, wait2 = limiter.acquire(est_prompt_tokens=100, max_tokens=200)
    t1 = time.time()
    # Second acquire must have waited for min_interval (0.1s)
    assert t1 - t0 >= 0.09
    assert wait2 > 0.0


def test_sliding_window_rpm_throttle():
    """Verify requests are throttled when RPM limit is reached."""
    # Window of 0.3s, max 2 requests
    limiter = GroqRateLimiter(rpm_limit=2, tpm_limit=50000, min_interval=0.01, window_seconds=0.3)

    # 1st and 2nd calls succeed immediately
    limiter.acquire(est_prompt_tokens=50, max_tokens=100)
    limiter.acquire(est_prompt_tokens=50, max_tokens=100)

    # 3rd call must wait for window to clear oldest request
    t0 = time.time()
    _, wait = limiter.acquire(est_prompt_tokens=50, max_tokens=100)
    elapsed = time.time() - t0

    assert elapsed >= 0.15
    assert wait > 0.0


def test_sliding_window_tpm_throttle_and_pruning():
    """Verify requests wait when rolling TPM limit would be exceeded."""
    # Window of 0.3s, max 1000 TPM
    limiter = GroqRateLimiter(rpm_limit=50, tpm_limit=1000, min_interval=0.01, window_seconds=0.3)

    # Acquire 700 tokens
    limiter.acquire(est_prompt_tokens=200, max_tokens=500)

    # Trying to acquire 400 more tokens (700 + 400 = 1100 > 1000) must wait until first expires
    t0 = time.time()
    _, wait = limiter.acquire(est_prompt_tokens=100, max_tokens=300)
    elapsed = time.time() - t0

    assert elapsed >= 0.15
    assert wait > 0.0


def test_token_reservation_clamping_to_headroom():
    """Verify max_tokens is clamped down if prompt + max_tokens > tpm_limit."""
    limiter = GroqRateLimiter(rpm_limit=50, tpm_limit=1000, min_interval=0.0, window_seconds=60.0)

    # Prompt is 800 tokens, limit is 1000. Clamped max_tokens should not exceed 150 (headroom)
    clamped_tokens, _ = limiter.acquire(est_prompt_tokens=800, max_tokens=500)
    assert clamped_tokens <= 200
    assert clamped_tokens >= 150


def test_server_header_telemetry():
    """Verify server headers update client telemetry and constrain future acquires."""
    limiter = GroqRateLimiter(rpm_limit=50, tpm_limit=6000, min_interval=0.0, window_seconds=60.0)

    headers = {
        "x-ratelimit-remaining-tokens": "800",
        "x-ratelimit-remaining-requests": "15",
        "x-ratelimit-reset-tokens": "2.5s",
    }
    limiter.update_from_headers(headers)

    assert limiter.server_remaining_tokens == 800
    assert limiter.server_remaining_requests == 15
    assert limiter.server_reset_tokens_s == 2.5


def test_parse_429_error_and_shrink_tokens():
    """Verify 429 message parsing extracts exact wait seconds and shrinks max_tokens."""
    # Example Groq 429 error message
    err_msg = (
        "Rate limit reached for model `llama-3.3-70b-versatile` on TPM: "
        "Limit 6000, Requested 7200. Please try again in 4.25s."
    )
    exc = Exception(err_msg)

    wait_s, suggested_tokens = parse_429_error(exc, prompt_len_estimate=500)

    # Wait seconds must reflect the 4.25s + jitter
    assert wait_s >= 4.25
    assert wait_s <= 5.5

    # Suggested tokens should shrink below the blowout
    assert suggested_tokens is not None
    assert suggested_tokens <= 6000 - 500


def test_groq_handler_success():
    """Verify GroqHandler successfully calls OpenAI client and returns text and tokens."""
    mock_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"status": "ok"}'))],
        usage=SimpleNamespace(prompt_tokens=25, completion_tokens=15),
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    limiter = GroqRateLimiter(min_interval=0.0)
    handler = GroqHandler(client_getter=lambda: mock_client, rate_limiter=limiter)

    text, in_tok, out_tok = handler.complete(
        system="sys",
        prompt="prompt",
        schema_name="planner",
        max_attempts=2,
    )

    assert text == '{"status": "ok"}'
    assert in_tok == 25
    assert out_tok == 15
    assert mock_client.chat.completions.create.call_count == 1


def test_groq_handler_recovers_from_429():
    """Verify GroqHandler retries on 429 and succeeds on next attempt."""
    mock_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Recovered after rate limit"))],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10),
    )

    call_count = 0

    def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Rate limit reached: Limit 6000, Requested 6500. Please try again in 0.05s.")
        return mock_resp

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = mock_create

    limiter = GroqRateLimiter(min_interval=0.0)
    handler = GroqHandler(client_getter=lambda: mock_client, rate_limiter=limiter)

    text, in_tok, out_tok = handler.complete(
        system="sys",
        prompt="prompt",
        schema_name="planner",
        max_attempts=3,
    )

    assert text == "Recovered after rate limit"
    assert call_count == 2


def test_groq_handler_fallback_model_on_repeated_429():
    """Verify GroqHandler falls back to 8b instant model on repeated 429 errors."""
    models_called = []

    def mock_create(**kwargs):
        models_called.append(kwargs.get("model"))
        if len(models_called) < 3:
            raise Exception("Rate limit reached on TPM. Try again in 0.02s.")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Fallback success"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = mock_create

    limiter = GroqRateLimiter(min_interval=0.0)
    handler = GroqHandler(client_getter=lambda: mock_client, rate_limiter=limiter)

    text, _, _ = handler.complete(
        system="sys",
        prompt="prompt",
        schema_name="planner",
        max_attempts=4,
    )

    assert text == "Fallback success"
    # Attempt 1 & 2 used default model, attempt 3 used fallback model (llama-3.1-8b-instant)
    assert models_called[0] == settings.GROQ_DEFAULT_MODEL
    assert models_called[1] == settings.GROQ_DEFAULT_MODEL
    assert models_called[2] == settings.GROQ_FALLBACK_MODEL


def test_llm_groq_complete_text_and_json(monkeypatch, tmp_path):
    """Integration test: LLM client routing to GroqHandler for text and JSON."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "runs_dir", runs_dir)
    monkeypatch.setattr(settings, "LLM_CACHE", "off")

    mock_resp_json = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"result": "groq_json_ok"}'))],
        usage=SimpleNamespace(prompt_tokens=30, completion_tokens=20),
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp_json

    llm = LLM()
    llm._provider = "groq"
    limiter = GroqRateLimiter(min_interval=0.0)
    handler = GroqHandler(client_getter=lambda: mock_client, rate_limiter=limiter)
    llm._groq_handler = handler

    run_id = "test-groq-run-01"
    json_result = llm.complete_json(
        system="sys",
        prompt="give json",
        schema_name="planner",
        run_id=run_id,
        max_tokens=4000,  # Will be clamped to schema budget 1500
    )

    assert json_result == {"result": "groq_json_ok"}
    u = usage(run_id)
    assert u.calls == 1
    assert u.inputTokens == 30
    assert u.outputTokens == 20
