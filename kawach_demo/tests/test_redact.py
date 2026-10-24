"""Tests for secret redaction helpers in kawach_demo."""

import pytest
from pydantic import SecretStr
from kawach_demo.redact import redact_text, redact_data


def test_redact_custom_secrets():
    pat = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    gemini_key = "AIzaSyAbcd1234567890_XYZqwerty12345"
    groq_key = "gsk_sampletestkey0987654321sampletestkey0987"

    raw_text = f"Connecting with token={pat} and llm={gemini_key} and groq={groq_key}"
    cleaned = redact_text(raw_text, [pat, gemini_key, groq_key])

    assert pat not in cleaned
    assert gemini_key not in cleaned
    assert groq_key not in cleaned
    assert "REDACTED" in cleaned


def test_redact_pattern_fallback():
    raw_text = (
        "Failed request: Authorization: Bearer ghp_SecretGitHubTokenForTesting123456789\n"
        "Groq key detected: gsk_abcdefghijklmnopqrstuvwxyz1234567890\n"
        "Google key: AIzaSyD987654321test_key_sample_12345"
    )
    # Pass empty explicit secrets list to test regex detection
    cleaned = redact_text(raw_text, [])

    assert "ghp_" not in cleaned
    assert "gsk_" not in cleaned
    assert "AIza" not in cleaned
    assert "REDACTED" in cleaned


def test_redact_data_nested():
    pat = "github_pat_11AEXAMPLE_PAT_SECRET_STRING_123456789"
    nested = {
        "user": "developer",
        "headers": {
            "Authorization": f"Bearer {pat}",
            "Other": "safe_value",
        },
        "logs": [
            f"Cloning repo with {pat}",
            "Clean line",
        ],
    }

    sanitized = redact_data(nested, [pat])
    assert pat not in str(sanitized)
    assert sanitized["user"] == "developer"
    assert sanitized["headers"]["Other"] == "safe_value"
    assert "REDACTED" in sanitized["headers"]["Authorization"]
    assert "REDACTED" in sanitized["logs"][0]
    assert sanitized["logs"][1] == "Clean line"

