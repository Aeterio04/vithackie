"""Playwright test runner interface and subprocess implementation."""

import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Protocol, runtime_checkable

from kawach_fix.schemas import RunItem


@runtime_checkable
class ScriptRunner(Protocol):
    """Protocol for executing Playwright tests in isolated environments."""

    async def run_test(
        self,
        script_path_or_code: str,
        target_url: str,
        project_dir: str,
        timeout_sec: int,
        run_index: int = 1,
    ) -> RunItem:
        """Run the Playwright test once and return execution metrics and outcome."""
        ...


class PlaywrightScriptRunner:
    """Production runner executing Playwright tests in a clean subprocess environment."""

    def _build_clean_env(self, target_url: str) -> Dict[str, str]:
        """Construct a minimal subprocess environment with no API tokens or keys."""
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
        timeout_sec: int,
        run_index: int = 1,
    ) -> RunItem:
        p_dir = Path(project_dir).resolve()
        is_file = False
        try:
            potential_path = Path(script_path_or_code)
            if potential_path.is_file() or (p_dir / script_path_or_code).is_file():
                is_file = True
        except Exception:
            is_file = False

        tmp_file: Optional[Path] = None
        if is_file:
            script_path = str(Path(script_path_or_code).resolve())
        else:
            # Inline script: write to a temporary .spec.ts inside project_dir
            temp_name = f"_kawach_verify_{run_index}_{int(time.time()*1000)}.spec.ts"
            tmp_file = p_dir / temp_name
            tmp_file.write_text(script_path_or_code, encoding="utf-8")
            script_path = str(tmp_file.resolve())

        clean_env = self._build_clean_env(target_url)
        start_time = time.perf_counter()

        # Build command
        if os.name == "nt":
            cmd = f'npx playwright test "{script_path}" --reporter=json'
            proc_coro = asyncio.create_subprocess_shell(
                cmd,
                cwd=str(p_dir),
                env=clean_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            proc_coro = asyncio.create_subprocess_exec(
                "npx",
                "playwright",
                "test",
                script_path,
                "--reporter=json",
                cwd=str(p_dir),
                env=clean_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        passed = False
        error_text: Optional[str] = None

        try:
            proc = await proc_coro
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout_sec)
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                passed = True
            else:
                passed = False
                # Try parsing playwright JSON reporter output
                extracted_err = self._extract_playwright_error(stdout_str)
                error_text = extracted_err or stderr_str.strip() or stdout_str.strip() or f"Process exited with code {proc.returncode}"
        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            passed = False
            error_text = f"Test execution timed out after {timeout_sec} seconds."
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            passed = False
            error_text = f"Execution failed: {str(e)}"
        finally:
            if tmp_file and tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass

        return RunItem(
            index=run_index,
            passed=passed,
            error_text=error_text if not passed else None,
            duration_ms=duration_ms,
        )

    def _extract_playwright_error(self, json_output: str) -> Optional[str]:
        """Attempt to extract the first failing spec error message from playwright json reporter."""
        try:
            data = json.loads(json_output)
            suites = data.get("suites", [])
            for suite in suites:
                for spec in suite.get("specs", []):
                    for test in spec.get("tests", []):
                        for res in test.get("results", []):
                            err = res.get("error", {})
                            if err and "message" in err:
                                return err["message"]
            errors = data.get("errors", [])
            if errors and isinstance(errors, list):
                first = errors[0]
                if isinstance(first, dict) and "message" in first:
                    return first["message"]
                if isinstance(first, str):
                    return first
        except Exception:
            pass
        return None
