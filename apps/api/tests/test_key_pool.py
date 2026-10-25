"""Comprehensive unit tests for the Groq multi-key pool (Problem 1).

Covers:
- Strict rotation order K1, K2, K3, K1, K2, K3 over 6 successful calls
- Immediate rollover on 429 to next key without sleeping (sub-millisecond)
- Cooling state and resumption after cooldown
- All keys 429 bounded wait & LLMRateLimitError upon cap exhaustion
- Daily limit (TPD/RPD) long cooldown (>= 10 minutes)
- 401/403 auto-disabling and graceful continuation
- Header parsing (Retry-After, 1m30s, 250ms, etc.)
- Multi-threaded concurrency: 60 parallel calls spread evenly across keys
- Absolute privacy: raw key secrets never leaked in logs, exceptions, or status responses
- Legacy single-key mode compatibility
- Grep test: zero direct calls to api.groq.com outside key_pool.py
- Protected GET /api/v1/llm/pool-status endpoint
"""

import concurrent.futures
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from pathlib import Path

from kawach.llm.key_pool import (
    KeyPool,
    LLMError,
    LLMRateLimitError,
    complete_with_pool,
    parse_reset_duration,
    mask_key,
)


class FakeGroqClient:
    """Mock Groq client implementing chat.completions.create with customizable behaviors."""

    def __init__(self, key_id: str, behavior=None):
        self.key_id = key_id
        self.behavior = behavior
        self.call_count = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.call_count += 1
        if self.behavior:
            return self.behavior(self.key_id, kwargs)

        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=f"reply_from_{self.key_id}"))],
            usage=SimpleNamespace(prompt_tokens=15, completion_tokens=10),
            _raw_response=SimpleNamespace(headers={
                "x-ratelimit-remaining-tokens": "5000",
                "x-ratelimit-remaining-requests": "29",
                "x-ratelimit-reset-tokens": "0.5s",
            }),
        )


def test_strict_rotation_order_over_six_calls():
    """Verify strict round-robin order K1, K2, K3, K1, K2, K3 over 6 calls."""
    calls_log = []

    def make_behavior(kid):
        def behavior(key_id, kwargs):
            calls_log.append(key_id)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=f"reply_{key_id}"))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
            )
        return behavior

    clients = {
        "k1": FakeGroqClient("k1", make_behavior("k1")),
        "k2": FakeGroqClient("k2", make_behavior("k2")),
        "k3": FakeGroqClient("k3", make_behavior("k3")),
    }

    pool = KeyPool(
        keys=["key_val_1", "key_val_2", "key_val_3"],
        client_factory=lambda k: clients["k1"] if "1" in k else (clients["k2"] if "2" in k else clients["k3"]),
    )

    for i in range(6):
        res, in_tok, out_tok = complete_with_pool(prompt="test", pool=pool)
        assert res.startswith("reply_k")

    assert calls_log == ["k1", "k2", "k3", "k1", "k2", "k3"]
    assert clients["k1"].call_count == 2
    assert clients["k2"].call_count == 2
    assert clients["k3"].call_count == 2


def test_immediate_rollover_on_429_without_sleep():
    """Call 2 hits 429 on K2 -> immediately retries on K3 without sleeping.
    
    K2 enters cooling state. Subsequent calls skip K2 until cooldown ends, then K2 resumes.
    """
    current_time = [1000.0]
    sleeps = []

    def fake_time():
        return current_time[0]

    def fake_sleep(sec):
        sleeps.append(sec)
        current_time[0] += sec

    k2_attempts = 0

    def k2_behavior(kid, kwargs):
        nonlocal k2_attempts
        k2_attempts += 1
        if k2_attempts == 1:
            err = Exception("Rate limit reached on TPM. Try again in 20.0s.")
            setattr(err, "status_code", 429)
            raise err
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="reply_k2_recovered"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
        )

    clients = {
        "k1": FakeGroqClient("k1"),
        "k2": FakeGroqClient("k2", k2_behavior),
        "k3": FakeGroqClient("k3"),
    }

    pool = KeyPool(
        keys=["key_val_1", "key_val_2", "key_val_3"],
        client_factory=lambda k: clients["k1"] if "1" in k else (clients["k2"] if "2" in k else clients["k3"]),
    )

    # Call 1 -> K1
    res1, _, _ = complete_with_pool(prompt="call 1", pool=pool, time_fn=fake_time, sleep_fn=fake_sleep)
    assert res1 == "reply_from_k1"
    assert len(sleeps) == 0

    # Call 2 -> K2 hits 429, IMMEDIATELY rolls over to K3 without sleeping!
    res2, _, _ = complete_with_pool(prompt="call 2", pool=pool, time_fn=fake_time, sleep_fn=fake_sleep)
    assert res2 == "reply_from_k3"
    assert len(sleeps) == 0  # CRITICAL ASSERTION: Zero sleep because K3 was available!

    # K2 is in cooling state
    status = pool.get_pool_status(now=current_time[0])
    k2_status = [k for k in status["keys"] if "key#2" in k["masked_id"]][0]
    assert k2_status["state"] == "cooling"
    assert k2_status["rate_limits_429"] == 1

    # Call 3 -> should pick K1 (rotation started after K3, wrapped to K1)
    res3, _, _ = complete_with_pool(prompt="call 3", pool=pool, time_fn=fake_time, sleep_fn=fake_sleep)
    assert res3 == "reply_from_k1"

    # Call 4 -> K2 still cooling, skips to K3!
    res4, _, _ = complete_with_pool(prompt="call 4", pool=pool, time_fn=fake_time, sleep_fn=fake_sleep)
    assert res4 == "reply_from_k3"

    # Fast forward time beyond K2 cooldown (20s)
    current_time[0] += 25.0

    # Call 5 -> rotation pointer was at K1 after K3 was used in Call 4
    res5, _, _ = complete_with_pool(prompt="call 5", pool=pool, time_fn=fake_time, sleep_fn=fake_sleep)
    assert res5 == "reply_from_k1"

    # Call 6 -> K2 cooldown has ended and pointer is at K2, rotation resumes with K2!
    res6, _, _ = complete_with_pool(prompt="call 6", pool=pool, time_fn=fake_time, sleep_fn=fake_sleep)
    assert res6 == "reply_k2_recovered"


def test_all_keys_429_waits_for_earliest_cooldown():
    """When all keys return 429, sleeps until earliest cooldown and retries."""
    current_time = [100.0]
    sleeps = []

    def fake_time():
        return current_time[0]

    def fake_sleep(sec):
        sleeps.append(sec)
        current_time[0] += sec

    attempt = 0

    def all_429_then_recover(kid, kwargs):
        nonlocal attempt
        attempt += 1
        if attempt <= 3:
            err = Exception("Rate limit reached. Try again in 5.0s.")
            setattr(err, "status_code", 429)
            raise err
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="recovered_all"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
        )

    pool = KeyPool(
        keys=["key_val_1", "key_val_2", "key_val_3"],
        client_factory=lambda k: FakeGroqClient(k, all_429_then_recover),
    )

    res, _, _ = complete_with_pool(prompt="test", pool=pool, time_fn=fake_time, sleep_fn=fake_sleep)
    assert res == "recovered_all"
    assert len(sleeps) == 1
    assert sleeps[0] >= 5.0


def test_permanent_429_raises_llm_rate_limit_error():
    """When all keys are permanently 429, raises LLMRateLimitError after max passes."""
    current_time = [100.0]

    def fake_time():
        return current_time[0]

    def fake_sleep(sec):
        current_time[0] += sec

    def perm_429(kid, kwargs):
        err = Exception("Rate limit reached. Try again in 10s.")
        setattr(err, "status_code", 429)
        raise err

    pool = KeyPool(
        keys=["key1", "key2"],
        client_factory=lambda k: FakeGroqClient(k, perm_429),
    )

    with pytest.raises(LLMRateLimitError) as exc_info:
        complete_with_pool(prompt="test", pool=pool, time_fn=fake_time, sleep_fn=fake_sleep)

    err_text = str(exc_info.value)
    assert "rate-limited" in err_text.lower()
    assert "exceeded wait cap" in err_text.lower() or "max passes" in err_text.lower()


def test_daily_limit_sets_long_cooldown():
    """Daily limit error (TPD/RPD) sets key cooldown to >= 600s (10 min)."""
    current_time = [100.0]

    def daily_err(kid, kwargs):
        err = Exception("Daily rate limit exceeded for tokens per day (TPD). Limit 500000.")
        setattr(err, "status_code", 429)
        raise err

    pool = KeyPool(
        keys=["k1"],
        client_factory=lambda k: FakeGroqClient(k, daily_err),
    )

    now = 100.0
    key = pool.keys[0]
    exc = Exception("Daily rate limit exceeded for tokens per day (TPD).")
    setattr(exc, "status_code", 429)
    cd = pool.handle_rate_limit(key, exc, now)

    assert cd >= 600.0
    assert key.cooldown_until >= now + 600.0


def test_401_disables_key_and_continues_with_others():
    """401 disables the failing key and other keys continue without crashing."""
    def k1_401(kid, kwargs):
        err = Exception("Invalid API key provided. (401)")
        setattr(err, "status_code", 401)
        raise err

    clients = {
        "k1": FakeGroqClient("k1", k1_401),
        "k2": FakeGroqClient("k2"),
    }

    pool = KeyPool(
        keys=["k1", "k2"],
        client_factory=lambda k: clients["k1"] if "k1" in k else clients["k2"],
    )

    # First call will hit K1 (401), disable it, and succeed on K2
    res, _, _ = complete_with_pool(prompt="test", pool=pool)
    assert res == "reply_from_k2"

    assert pool.keys[0].disabled is True
    assert pool.keys[1].disabled is False

    # Second call should use K2 directly
    res2, _, _ = complete_with_pool(prompt="test 2", pool=pool)
    assert res2 == "reply_from_k2"


def test_all_keys_disabled_raises_clear_error():
    """When all keys are 401 disabled, raises a clear error."""
    def auth_err(kid, kwargs):
        err = Exception("Unauthorized key 401")
        setattr(err, "status_code", 401)
        raise err

    pool = KeyPool(
        keys=["k1"],
        client_factory=lambda k: FakeGroqClient(k, auth_err),
    )

    with pytest.raises(LLMError) as exc_info:
        complete_with_pool(prompt="test", pool=pool)

    assert "disabled" in str(exc_info.value).lower()


def test_header_duration_parsing():
    """Verify parse_reset_duration correctly handles Groq header reset formats."""
    assert parse_reset_duration("250ms") == 0.25
    assert parse_reset_duration("1m30s") == 90.0
    assert parse_reset_duration("2m") == 120.0
    assert parse_reset_duration("45s") == 45.0
    assert parse_reset_duration("1.5s") == 1.5
    assert parse_reset_duration(30) == 30.0
    assert parse_reset_duration("60") == 60.0
    assert parse_reset_duration(None) is None


def test_concurrency_parallel_distribution():
    """60 parallel threads calling complete_with_pool distribute evenly across 3 keys."""
    clients = {
        "k1": FakeGroqClient("k1"),
        "k2": FakeGroqClient("k2"),
        "k3": FakeGroqClient("k3"),
    }

    pool = KeyPool(
        keys=["key_val_1", "key_val_2", "key_val_3"],
        client_factory=lambda k: clients["k1"] if "1" in k else (clients["k2"] if "2" in k else clients["k3"]),
    )

    def worker(i):
        return complete_with_pool(prompt=f"call {i}", pool=pool)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(worker, range(60)))

    assert len(results) == 60
    # Every key should receive 20 requests exactly in a 60-call clean round-robin
    assert clients["k1"].call_count == 20
    assert clients["k2"].call_count == 20
    assert clients["k3"].call_count == 20


def test_keys_never_appear_in_logs_metrics_or_status(caplog):
    """Raw API keys must never be exposed in logs, exceptions, or pool-status responses."""
    secret_k1 = "gsk_super_secret_alpha_key_9876"
    secret_k2 = "gsk_super_secret_beta_key_5432"

    def fail_auth(kid, kwargs):
        err = Exception(f"Failed authorization with {kid}")
        setattr(err, "status_code", 401)
        raise err

    pool = KeyPool(
        keys=[secret_k1, secret_k2],
        client_factory=lambda k: FakeGroqClient(k, fail_auth),
    )

    with pytest.raises(LLMError):
        complete_with_pool(prompt="test", pool=pool)

    # Check pool status
    status = pool.get_pool_status()
    status_str = str(status)

    assert secret_k1 not in status_str
    assert secret_k2 not in status_str
    assert "key#1 ...9876" in status_str
    assert "key#2 ...5432" in status_str

    # Check captured logs
    captured_logs = caplog.text
    assert secret_k1 not in captured_logs
    assert secret_k2 not in captured_logs


def test_single_key_legacy_mode():
    """Verify backwards compatibility: legacy single key functions as a pool of one."""
    mock_client = FakeGroqClient("legacy_key")
    pool = KeyPool(keys=["legacy_secret_key"], client_factory=lambda k: mock_client)

    assert pool.size() == 1
    res, _, _ = complete_with_pool(prompt="hello", pool=pool)
    assert res == "reply_from_legacy_key"
    assert mock_client.call_count == 1


def test_grep_no_direct_groq_api_outside_wrapper():
    """Ensure no code outside key_pool.py calls the Groq API (api.groq.com) directly."""
    repo_root = Path(__file__).resolve().parents[3]
    allowed_file = (repo_root / "apps" / "api" / "src" / "kawach" / "llm" / "key_pool.py").resolve()

    violations = []
    py_files = list((repo_root / "apps" / "api" / "src").rglob("*.py"))
    py_files += list((repo_root / "fix_pipeline" / "src").rglob("*.py"))
    py_files += list((repo_root / "kawach_demo" / "src").rglob("*.py"))

    for py_file in py_files:
        if py_file.resolve() == allowed_file:
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        if "api.groq.com" in content:
            violations.append(str(py_file))

    assert not violations, f"Found direct Groq API references outside wrapper module: {violations}"


def test_pool_status_api_endpoint():
    """Verify GET /api/v1/llm/pool-status enforces auth and returns safe telemetry."""
    from fastapi.testclient import TestClient
    from kawach.main import app
    from kawach.api.deps import get_current_user
    from kawach.db.models.identity import User

    client = TestClient(app)

    # 1. Unauthenticated -> 401
    res_unauth = client.get("/api/v1/llm/pool-status")
    assert res_unauth.status_code == 401

    # 2. Authenticated -> 200 with masked keys
    mock_user = User(id="user_test_01", email="tester@example.com", password_hash="hash")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        res = client.get("/api/v1/llm/pool-status")
        assert res.status_code == 200
        data = res.json()
        assert "total_keys" in data
        assert "keys" in data
        assert isinstance(data["keys"], list)
        for k in data["keys"]:
            assert "masked_id" in k
            assert "state" in k
            assert "seconds_until_ready" in k
            assert "requests" in k
            assert "rate_limits_429" in k
            # Ensure raw secret is NEVER in response
            assert not k["masked_id"].startswith("gsk_")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

