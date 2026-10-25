"""Circuit breaker and environment gate check for KAWACH.

Implements Phase 2 (Item 6) & Phase 4:
- Pre-suite gate navigation: If the gate fails with an environment-class error
  (blocked_by_waf, bad_gateway_from_target, dns_error, tls_error, timeout, empty_page),
  halts test generation/execution, creates ONE run-level finding in environment_issue.json,
  sets run stage to 'done_with_environment_issue', and marks 0 tests failed.
- In-suite circuit breaker: If 3 consecutive tests fail with environment-class errors on
  the first navigation, aborts remaining tests as 'not_run' with reason.
- Generates plain-language owner guidance for WAF/firewall allow-listing.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
import urllib.parse

from kawach.core.config import settings
from kawach.core.target_fetch import check_target_reachability
from kawach.storage import artifacts as storage


def generate_owner_guidance(classification: str, target_url: str, qa_token: Optional[str] = None) -> str:
    """Generate clear, actionable instructions for the site owner."""
    token = qa_token or getattr(settings, "QA_TOKEN", "kw_qa_" + os.urandom(6).hex())
    guidance = (
        f"### Site Owner Guidance for {target_url}\n\n"
        f"The automated QA suite detected an environment-level barrier: **{classification}**.\n\n"
        "To allow the QA platform to test this application honestly without evasion:\n\n"
        f"1. **Custom Header Rule (Recommended)**:\n"
        f"   Configure your WAF / CDN (Cloudflare, AWS WAF, Fastly, Akamai) with a bypass rule for automated test traffic:\n"
        f"   ```http\n"
        f"   Header Name : X-QA-Token\n"
        f"   Header Value: {token}\n"
        f"   ```\n"
        f"   Set the action to *Skip / Allow* for requests carrying this secret token.\n\n"
        "2. **Staging / Preview Environment**:\n"
        "   Deploy to a dedicated staging or preview environment (e.g. Vercel Preview, staging subdomain) where bot-challenge rules are disabled.\n\n"
        "3. **IP Allow-listing**:\n"
        "   If running on a private runner or dedicated server, allow-list the runner's egress IP in your firewall.\n"
    )
    return guidance


def run_gate_check(run_id: str, target_url: str) -> Optional[Dict[str, Any]]:
    """Execute pre-suite gate check.

    Returns finding dictionary if environment issue detected and sets stage to
    'done_with_environment_issue'. Returns None if target is healthy.
    """
    def _log(msg: str, **kwargs):
        try:
            from kawach.storage.artifacts import log_pipeline
            log_pipeline(run_id, msg, **kwargs)
        except Exception:
            pass

    _log(f"Circuit Breaker: Running pre-suite gate check against {target_url}...", source="circuit_breaker")

    # 1. HTTP and SSRF probe
    http_probe = check_target_reachability(target_url)

    classification: Optional[str] = None
    reason: Optional[str] = None

    if not http_probe.allowed:
        classification = "blocked_by_ssrf"
        reason = http_probe.reason or "Destination blocked by SSRF policy."
    elif not http_probe.reachable:
        res_lower = (http_probe.reason or "").lower()
        if "dns" in res_lower or "name resolution" in res_lower:
            classification = "dns_error"
        elif "ssl" in res_lower or "tls" in res_lower or "certificate" in res_lower:
            classification = "tls_error"
        elif "timeout" in res_lower or "timed out" in res_lower:
            classification = "timeout"
        elif http_probe.status_code in (502, 504):
            classification = "bad_gateway_from_target"
        elif http_probe.status_code in (403, 429, 503):
            classification = "blocked_by_waf"
        else:
            classification = "target_unreachable"
        reason = http_probe.reason or f"Target unreachable (HTTP {http_probe.status_code})"
    elif http_probe.status_code in (502, 504):
        classification = "bad_gateway_from_target"
        reason = f"Target returned HTTP {http_probe.status_code} Bad Gateway / Gateway Timeout."

    # 2. Browser gate navigation probe
    if not classification:
        script_path = settings.repo_root / "apps" / "runner" / "diagnose_playwright.mjs"
        runner_cwd = settings.repo_root / "apps" / "runner"
        gate_out_dir = storage.run_dir(run_id) / "gate"
        gate_out_dir.mkdir(parents=True, exist_ok=True)

        cmd = ["node", str(script_path), target_url, str(gate_out_dir)]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(runner_cwd),
                capture_output=True,
                text=True,
                timeout=75,  # script waits (goto 25 + load 10 + idle 3 + screenshot) must fit inside this
            )
            stdout = proc.stdout
            marker_start = "__PLAYWRIGHT_DIAG_OUTPUT_START__"
            marker_end = "__PLAYWRIGHT_DIAG_OUTPUT_END__"
            if marker_start in stdout and marker_end in stdout:
                json_str = stdout.split(marker_start)[1].split(marker_end)[0].strip()
                diag_data = json.loads(json_str)
                new_std = diag_data.get("new_standard", {})
                status = new_std.get("status")
                text_len = new_std.get("textLength", 0)
                vis_els = new_std.get("visibleElements", 0)
                err = new_std.get("error")

                if err:
                    err_l = err.lower()
                    if "net::err_name_not_resolved" in err_l:
                        classification = "dns_error"
                        reason = f"DNS resolution failed in browser: {err}"
                    elif "net::err_cert_" in err_l or "ssl" in err_l:
                        classification = "tls_error"
                        reason = f"TLS handshake failed in browser: {err}"
                    elif "net::err_connection_timed_out" in err_l or "timeout" in err_l:
                        classification = "timeout"
                        reason = f"Browser connection timed out: {err}"
                    elif "net::err_connection_refused" in err_l:
                        classification = "bad_gateway_from_target"
                        reason = f"Connection refused by target: {err}"

                if not classification:
                    if status in (403, 429, 503):
                        classification = "blocked_by_waf"
                        reason = f"Browser session intercepted by WAF / security challenge (HTTP {status})."
                    elif status in (502, 504):
                        classification = "bad_gateway_from_target"
                        reason = f"Browser received HTTP {status} Bad Gateway."
                    elif status == 200 and text_len == 0 and vis_els <= 1:
                        classification = "empty_page"
                        reason = "Page returned 200 OK but rendered an empty/blank body."
        except subprocess.TimeoutExpired:
            classification = "timeout"
            reason = "Browser gate navigation timed out after 75s."
        except Exception as e:
            _log(f"Notice: Gate browser check threw exception: {e}", level="warning")

    # If an environment issue was detected, halt and trip the circuit breaker
    if classification:
        guidance = generate_owner_guidance(classification, target_url)
        finding = {
            "title": f"Target not testable: {classification}",
            "classification": classification,
            "reason": reason,
            "targetUrl": target_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "guidance": guidance,
            "origin": http_probe.origin if http_probe else "target",
        }

        # Save finding to run directory
        finding_file = storage.run_dir(run_id) / "environment_issue.json"
        with open(finding_file, "w", encoding="utf-8") as f:
            json.dump(finding, f, indent=2)

        # Set stage to done_with_environment_issue
        storage.set_stage(
            run_id,
            "done_with_environment_issue",  # type: ignore
            step=f"Target not testable: {classification} ({reason})",
        )

        _log(
            f"Circuit Breaker TRIPPED: Target is not testable ({classification}). Stopping suite to prevent false failures.",
            level="error",
            source="circuit_breaker",
        )

        # Build clean environment report
        from kawach.execution.reporting import build_report, build_metrics
        try:
            build_metrics(run_id)
            build_report(run_id)
        except Exception:
            pass

        return finding

    _log("Circuit Breaker: Pre-suite gate check passed. Target is online and testable.", source="circuit_breaker")
    try:
        storage.write_json(run_id, "gate_result.json", {
            "status": "passed", "targetUrl": target_url, "at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass
    return None
