"""Unit tests for Kawach MCP configuration and secure token file loading."""

import os
import stat
from pathlib import Path
import pytest
from kawach_mcp.config import Settings, _resolve_token_from_file


def test_config_defaults(monkeypatch):
    """Test default settings when no env vars are set."""
    monkeypatch.delenv("KAWACH_API_URL", raising=False)
    monkeypatch.delenv("KAWACH_API_TOKEN", raising=False)
    monkeypatch.delenv("KAWACH_ALLOW_WRITE_TOOLS", raising=False)
    monkeypatch.delenv("KAWACH_MAX_RESPONSE_CHARS", raising=False)

    s = Settings()
    assert s.clean_api_url == "http://localhost:8000"
    assert s.api_token is None
    assert s.allow_write_tools is False
    assert s.max_response_chars == 4000


def test_config_env_override(monkeypatch):
    """Test that environment variables override defaults."""
    monkeypatch.setenv("KAWACH_API_URL", "http://my-api:9000/")
    monkeypatch.setenv("KAWACH_API_TOKEN", "kw_live_test_secret_123")
    monkeypatch.setenv("KAWACH_ALLOW_WRITE_TOOLS", "true")
    monkeypatch.setenv("KAWACH_MAX_RESPONSE_CHARS", "8000")

    s = Settings()
    assert s.clean_api_url == "http://my-api:9000"
    assert s.get_effective_token() == "kw_live_test_secret_123"
    assert s.allow_write_tools is True
    assert s.max_response_chars == 8000


def test_resolve_token_from_file(tmp_path):
    """Test loading token from an explicit file."""
    token_file = tmp_path / "secret_token"
    token_file.write_text("kw_live_file_token_456\n", encoding="utf-8")

    token = _resolve_token_from_file(str(token_file))
    assert token == "kw_live_file_token_456"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permission checks do not apply to Windows NTFS ACLs")
def test_resolve_token_insecure_permissions_rejected(tmp_path):
    """Verify that file permissions wider than 0600 are rejected on POSIX."""
    token_file = tmp_path / "insecure_token"
    token_file.write_text("kw_live_insecure_token", encoding="utf-8")
    # Make file world-readable (0644)
    token_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH)

    with pytest.raises(PermissionError, match="must be 0600"):
        _resolve_token_from_file(str(token_file))
