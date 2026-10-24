"""Robust Playwright script runner handling Windows paths and JSON reporting."""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional
from rich.console import Console

from kawach_fix.clients.runner import ScriptRunner
from kawach_fix.schemas import RunItem

console = Console()


class RobustPlaywrightRunner(ScriptRunner):
    """Playwright runner that converts Windows paths to POSIX format to prevent regex escaping bugs."""

    def _build_clean_env(self, target_url: str) -> Dict[str, str]:
        safe_keys = {
            "PATH",
            "HOME",
            "USERPROFILE",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "LOCALAPPDATA",
            "APPDATA",
            "NODE_PATH",
        }
        clean_env: Dict[str, str] = {}
        for k, v in os.environ.items():
            if k.upper() in safe_keys:
                clean_env[k] = v

        clean_env["BASE_URL"] = target_url
        clean_env["CI"] = "1"
        return clean_env

    async def run_test(
        self,
        script_path_or_code: str,
        target_url: str,
        project_dir: str,
        timeout_sec: int = 30,
        run_index: int = 1,
    ) -> RunItem:
        p_dir = Path(project_dir).resolve()
        is_file = False
        try:
            p_obj = Path(script_path_or_code)
            if p_obj.is_file() or (p_dir / script_path_or_code).is_file():
                is_file = True
        except Exception:
            is_file = False

        if is_file:
            # Use relative POSIX path if within project_dir, or absolute POSIX path
            resolved = (p_dir / script_path_or_code).resolve() if (p_dir / script_path_or_code).is_file() else Path(script_path_or_code).resolve()
            try:
                rel = resolved.relative_to(p_dir)
                spec_arg = rel.as_posix()
            except ValueError:
                spec_arg = resolved.as_posix()
        else:
            temp_name = f"_kawach_verify_{run_index}_{int(time.time()*1000)}.spec.ts"
            tmp_file = p_dir / temp_name
            tmp_file.write_text(script_path_or_code, encoding="utf-8")
            spec_arg = temp_name

        clean_env = self._build_clean_env(target_url)
        start_time = time.perf_counter()

        cmd = f'npx playwright test "{spec_arg}" --reporter=json'
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=str(p_dir),
            env=clean_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        passed = False
        error_text: Optional[str] = None

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout_sec)
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                passed = True
            else:
                # Parse JSON output for detailed error
                try:
                    data = json.loads(stdout_str)
                    errors = []
                    for suite in data.get("suites", []):
                        for spec in suite.get("specs", []):
                            for test in spec.get("tests", []):
                                for r in test.get("results", []):
                                    if r.get("status") in ("failed", "timedOut"):
                                        err = r.get("error", {})
                                        snippet = err.get("snippet", "")
                                        msg = err.get("message", "")
                                        errors.append(f"{msg}\n{snippet}".strip())
                    error_text = "\n---\n".join(errors) if errors else (stderr_str or stdout_str)
                except Exception:
                    error_text = stderr_str or stdout_str

        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            try:
                proc.kill()
            except Exception:
                pass
            passed = False
            error_text = f"Test timed out after {timeout_sec}s"
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            passed = False
            error_text = f"Execution error: {e}"

        return RunItem(
            index=run_index,
            passed=passed,
            error_text=error_text,
            duration_ms=duration_ms,
        )
