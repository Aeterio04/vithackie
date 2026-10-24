"""Offline tests for GitOpsManager ensuring git commands never leak secrets."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pydantic import SecretStr

from kawach_demo.gitops import GitOpsManager, GitOpsError


def test_gitops_never_puts_pat_in_command_argv(tmp_path):
    pat_str = "ghp_SecretMockPATThatShouldNeverAppearInArgv12345"
    manager = GitOpsManager(tmp_path, SecretStr(pat_str))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="clean", stderr="")
        manager.run_git("push", "origin", "main")

        assert mock_run.called
        cmd_args, kwargs = mock_run.call_args
        called_cmd = cmd_args[0]

        # Verify command line arguments
        assert "git" in called_cmd[0]
        for arg in called_cmd:
            assert pat_str not in arg

        # Verify environment contains askpass and env variable
        env = kwargs.get("env", {})
        assert env.get("KAWACH_DEMO_GIT_PAT") == pat_str
        assert "GIT_ASKPASS" in env
        assert env.get("GIT_TERMINAL_PROMPT") == "0"


def test_gitops_error_redacts_pat_in_exception(tmp_path):
    pat_str = "ghp_SecretMockPATThatShouldNeverAppearInArgv12345"
    manager = GitOpsManager(tmp_path, SecretStr(pat_str))

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr=f"fatal: Authentication failed for token {pat_str}",
        )
        with pytest.raises(GitOpsError) as exc_info:
            manager.run_git("push", "origin", "main")

        err_msg = str(exc_info.value)
        assert pat_str not in err_msg
        assert "REDACTED" in err_msg
