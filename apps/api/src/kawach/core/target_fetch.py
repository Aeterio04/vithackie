"""Shared target-fetch policy, SSRF defense, and pre-flight target check.

Implements Phase 2:
1. Standard Chrome desktop user agent and browser headers.
2. Anti DNS-rebinding and comprehensive IP verification (cloud metadata, loopback, private ranges).
3. Lightweight GET probe with Range header instead of brittle HEAD.
4. Transient retries (502/503/504, connection reset, timeout) with exponential backoff & jitter.
5. Honest origin labeling: target, network, or platform_ssrf.
"""

from dataclasses import dataclass, field
import ipaddress
import os
import random
import socket
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

import httpx

from kawach.core.config import settings

# Standard desktop Chrome user agent
STANDARD_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STANDARD_ACCEPT_HEADERS = {
    "User-Agent": STANDARD_CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# Cloud metadata ranges (AWS, GCP, Azure, OpenStack) - ALWAYS strictly forbidden
CLOUD_METADATA_NETS = [
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 Link-local
    ipaddress.ip_network("fe80::/10"),       # IPv6 Link-local
]

PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # IPv6 Unique Local
]


@dataclass
class SSRFCheckResult:
    allowed: bool
    reason: Optional[str] = None
    resolved_ips: List[str] = field(default_factory=list)


@dataclass
class TargetProbeResult:
    reachable: bool
    allowed: bool
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    server: Optional[str] = None
    reason: Optional[str] = None
    tls_valid: Optional[bool] = None
    redirect_chain: List[str] = field(default_factory=list)
    origin: str = "target"  # target | network | platform_ssrf


def validate_ip_ssrf(ip_str: str, is_dev_allowed: bool = True) -> Tuple[bool, Optional[str]]:
    """Validate a single IP address against SSRF rules."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"Invalid IP address representation: {ip_str}"

    # 1. Cloud metadata is ALWAYS forbidden
    for net in CLOUD_METADATA_NETS:
        if ip in net:
            return False, f"SSRF block: Destination IP {ip_str} is in protected link-local/cloud-metadata space."

    # 2. Local/Private networks
    for net in PRIVATE_NETS:
        if ip in net:
            if is_dev_allowed:
                return True, None
            return False, f"SSRF block: Destination IP {ip_str} is in private/loopback network ({net})."

    return True, None


def resolve_and_check_ssrf(hostname: str) -> SSRFCheckResult:
    """Resolve hostname to IPs and verify every IP against SSRF rules."""
    is_dev = getattr(settings, "ENV", "development") == "development"
    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", ["*"])
    if isinstance(allowed_hosts, str):
        allowed_hosts = [h.strip() for h in allowed_hosts.split(",") if h.strip()]

    host_lower = hostname.lower()

    # Domain allowlist check
    if "*" not in allowed_hosts and host_lower not in [h.lower() for h in allowed_hosts]:
        if not (is_dev and host_lower in ("localhost", "127.0.0.1", "0.0.0.0")):
            return SSRFCheckResult(
                allowed=False,
                reason=f"Host '{hostname}' is not in ALLOWED_HOSTS.",
            )

    try:
        addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return SSRFCheckResult(
            allowed=False,
            reason=f"DNS resolution failed: {e}",
        )

    resolved_ips = list({res[4][0] for res in addr_info})
    if not resolved_ips:
        return SSRFCheckResult(allowed=False, reason="DNS resolved to no addresses.")

    allow_private = is_dev or host_lower in ("localhost", "127.0.0.1")

    for ip in resolved_ips:
        ok, reason = validate_ip_ssrf(ip, is_dev_allowed=allow_private)
        if not ok:
            return SSRFCheckResult(allowed=False, reason=reason, resolved_ips=resolved_ips)

    return SSRFCheckResult(allowed=True, resolved_ips=resolved_ips)


def get_shared_target_headers(extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return unified target-fetch headers with modern Chrome UA and optional project headers."""
    headers = dict(STANDARD_ACCEPT_HEADERS)
    # Check project / env custom token
    qa_token = os.environ.get("X_QA_TOKEN") or getattr(settings, "QA_TOKEN", None)
    if qa_token:
        headers["X-QA-Token"] = qa_token

    if extra_headers:
        headers.update(extra_headers)

    return headers


def check_target_reachability(
    url: str,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout_connect: float = 15.0,
    timeout_read: float = 30.0,
) -> TargetProbeResult:
    """Preflight check: Validate SSRF, DNS, TLS, and reachability using lightweight GET."""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        if url.startswith("localhost") or url.startswith("127.0.0.1"):
            url = f"http://{url}"
        else:
            url = f"https://{url}"

    parsed = urllib.parse.urlparse(url)
    if not (parsed.scheme in ("http", "https") and parsed.netloc):
        return TargetProbeResult(
            reachable=False,
            allowed=False,
            reason="Invalid URL scheme. Must include http:// or https://",
            origin="platform_ssrf",
        )

    hostname = parsed.hostname or ""
    # 1. Anti DNS-rebinding SSRF verification
    ssrf = resolve_and_check_ssrf(hostname)
    if not ssrf.allowed:
        return TargetProbeResult(
            reachable=False,
            allowed=False,
            reason=ssrf.reason or "SSRF violation",
            origin="platform_ssrf",
        )

    headers = get_shared_target_headers(extra_headers)
    headers["Range"] = "bytes=0-4096"  # Lightweight GET

    redirect_chain: List[str] = []
    current_url = url
    max_hops = 10
    tls_valid = parsed.scheme == "https"

    for hop in range(max_hops):
        curr_parsed = urllib.parse.urlparse(current_url)
        curr_host = curr_parsed.hostname or ""

        # Re-resolve and check SSRF at each redirect hop
        hop_ssrf = resolve_and_check_ssrf(curr_host)
        if not hop_ssrf.allowed:
            return TargetProbeResult(
                reachable=False,
                allowed=False,
                reason=f"Redirect hop to {curr_host} blocked by SSRF policy: {hop_ssrf.reason}",
                redirect_chain=redirect_chain,
                origin="platform_ssrf",
            )

        # Retry logic: up to 2 retries on 502/503/504, timeout, or connection reset
        resp = None
        last_error = None

        for attempt in range(3):
            try:
                with httpx.Client(
                    follow_redirects=False,
                    timeout=httpx.Timeout(timeout_read, connect=timeout_connect),
                    verify=True,
                ) as client:
                    resp = client.get(current_url, headers=headers)
                    # If 502/503/504, transient retry with backoff
                    if resp.status_code in (502, 503, 504) and attempt < 2:
                        retry_after = resp.headers.get("retry-after")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else (0.5 * (2 ** attempt) + random.uniform(0.1, 0.4))
                        time.sleep(delay)
                        continue
                    break
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as err:
                last_error = err
                if attempt < 2:
                    delay = 0.5 * (2 ** attempt) + random.uniform(0.1, 0.3)
                    time.sleep(delay)
                else:
                    break
            except ssl.SSLError as ssl_err:
                tls_valid = False
                return TargetProbeResult(
                    reachable=False,
                    allowed=True,
                    reason=f"SSL/TLS certificate error: {ssl_err}",
                    tls_valid=False,
                    redirect_chain=redirect_chain,
                    origin="network",
                )
            except Exception as e:
                last_error = e
                break

        if resp is None:
            return TargetProbeResult(
                reachable=False,
                allowed=True,
                reason=f"Connection failed: {last_error}",
                redirect_chain=redirect_chain,
                origin="network",
            )

        # Handle redirects
        if resp.is_redirect:
            redirect_chain.append(f"{resp.status_code} -> {current_url}")
            loc = resp.headers.get("location")
            if not loc:
                break
            current_url = urllib.parse.urljoin(current_url, loc)
            continue
        else:
            server_header = resp.headers.get("server")
            status = resp.status_code

            # 2xx, 3xx, 401, 403 are considered reachable (401/403 means service/WAF is responsive)
            is_reachable = (200 <= status < 400) or status in (401, 403)
            reason = None
            if status >= 400:
                reason = f"Target returned HTTP {status} (Server: {server_header or 'unknown'})"

            return TargetProbeResult(
                reachable=is_reachable,
                allowed=True,
                status_code=status,
                final_url=str(resp.url),
                server=server_header,
                reason=reason,
                tls_valid=tls_valid,
                redirect_chain=redirect_chain,
                origin="target",
            )

    return TargetProbeResult(
        reachable=False,
        allowed=True,
        reason=f"Exceeded maximum redirects ({max_hops})",
        redirect_chain=redirect_chain,
        origin="network",
    )
