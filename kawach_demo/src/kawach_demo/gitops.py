"""GitOps manager for manipulating the target demo clone via Git CLI and GIT_ASKPASS."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import SecretStr

from kawach_demo.redact import redact_text


class GitOpsError(Exception):
    """Exception raised when a git command fails."""
    pass


class GitOpsManager:
    """Manages local clone git operations safely using GIT_ASKPASS authentication."""

    def __init__(self, clone_path: Path, pat: SecretStr):
        self.clone_path = Path(clone_path).resolve()
        self.pat_str = pat.get_secret_value()
        self._askpass_script: Optional[Path] = None

    def _get_askpass_script(self) -> Path:
        """Create a transient python askpass helper that prints credentials from env."""
        if self._askpass_script is not None and self._askpass_script.exists():
            return self._askpass_script

        script_content = (
            "import os, sys\n"
            "prompt = sys.argv[1] if len(sys.argv) > 1 else ''\n"
            "if 'Username' in prompt:\n"
            "    sys.stdout.write('x-access-token\\n')\n"
            "else:\n"
            "    sys.stdout.write(os.environ.get('KAWACH_DEMO_GIT_PAT', '') + '\\n')\n"
        )
        tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".py")
        tmp.write(script_content)
        tmp.close()
        self._askpass_script = Path(tmp.name)
        return self._askpass_script

    def run_git(self, *args: str, check: bool = True) -> str:
        """Run a git command in the clone directory with GIT_ASKPASS authentication."""
        askpass = self._get_askpass_script()

        env = os.environ.copy()
        env["GIT_ASKPASS"] = sys.executable
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["KAWACH_DEMO_GIT_PAT"] = self.pat_str

        # On Windows, git invokes python via command line; we supply askpass as GIT_ASKPASS
        # By setting GIT_ASKPASS to a small python wrapper
        # Or creating a .bat / .cmd on Windows
        if os.name == "nt":
            bat_path = askpass.with_suffix(".bat")
            if not bat_path.exists():
                bat_path.write_text(f'@"{sys.executable}" "{askpass}" %*', encoding="utf-8")
            env["GIT_ASKPASS"] = str(bat_path)

        cmd = ["git"] + list(args)
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.clone_path),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if check and res.returncode != 0:
                err_msg = redact_text(res.stderr or res.stdout, [self.pat_str])
                raise GitOpsError(f"git {' '.join(args)} failed (exit {res.returncode}): {err_msg.strip()}")
            return redact_text(res.stdout, [self.pat_str]).strip()
        except Exception as e:
            if isinstance(e, GitOpsError):
                raise
            raise GitOpsError(f"Failed to execute git command: {redact_text(str(e), [self.pat_str])}")

    def verify_clean(self) -> bool:
        """Return True if working tree has no uncommitted or untracked changes."""
        status = self.run_git("status", "--porcelain")
        return len(status.strip()) == 0

    def get_current_sha(self) -> str:
        """Return the current commit hash (HEAD)."""
        return self.run_git("rev-parse", "HEAD")

    def get_current_branch(self) -> str:
        """Return the current branch name."""
        return self.run_git("rev-parse", "--abbrev-ref", "HEAD")

    def check_tag_exists(self, tag: str = "demo-good") -> bool:
        """Return True if specified tag exists locally."""
        tags = self.run_git("tag", "-l", tag)
        return tag in tags.split()

    def plant_bug(self, patch_file: Path, commit_msg: str) -> str:
        """Apply a bug patch file, stage, commit, and push to origin main."""
        patch_abs = Path(patch_file).resolve()
        if not patch_abs.is_file():
            raise GitOpsError(f"Patch file not found: {patch_abs}")

        self.run_git("checkout", "main")
        self.run_git("apply", "--whitespace=nowarn", str(patch_abs))
        self.run_git("add", "-A")
        self.run_git("commit", "-m", commit_msg)
        self.run_git("push", "origin", "main")
        return self.get_current_sha()

    def pull(self) -> str:
        """Pull latest commits from origin/main."""
        return self.run_git("pull", "origin", "main")

    def apply_edits_locally(self, edits: List[Any]) -> None:
        """Apply exact search-and-replace edits to working tree files."""
        for edit in edits:
            rel_path = edit.path if hasattr(edit, "path") else edit["path"]
            old_str = edit.old_str if hasattr(edit, "old_str") else edit["old_str"]
            new_str = edit.new_str if hasattr(edit, "new_str") else edit["new_str"]

            target_file = self.clone_path / rel_path
            if not target_file.is_file():
                raise GitOpsError(f"Cannot apply edit to non-existent file: {rel_path}")

            content = target_file.read_text(encoding="utf-8")
            if old_str not in content:
                raise GitOpsError(f"old_str not found in {rel_path}")

            new_content = content.replace(old_str, new_str, 1)
            target_file.write_text(new_content, encoding="utf-8")

    def revert_working_tree(self) -> None:
        """Discard uncommitted modifications and untracked files in working tree."""
        self.run_git("checkout", "--", ".")
        self.run_git("clean", "-fd")

    def reset_to_tag(self, tag: str = "demo-good") -> None:
        """Force-reset local clone and origin/main to the tagged good state."""
        self.run_git("checkout", "main")
        self.run_git("reset", "--hard", tag)
        # Attempt force-with-lease first, fallback to force if needed
        try:
            self.run_git("push", "--force-with-lease", "origin", "main")
        except GitOpsError:
            self.run_git("push", "--force", "origin", "main")

        self.revert_working_tree()
