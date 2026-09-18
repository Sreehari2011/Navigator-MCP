"""WAF / CDN detection.

Two layers:
  1. **Header fingerprinting** — always available, no external tools. Matches
     characteristic response headers of the major WAFs/CDNs.
  2. **wafw00f** (optional) — if the ``wafw00f`` binary is installed
     (``pip install navigator-mcp[waf]``), its output is merged in.

Returns a directive the LLM can act on (slow down, obfuscate, route around).
"""

from __future__ import annotations

import re
import shutil
from typing import Any

WAF_SIGNATURES: list[dict[str, Any]] = [
    {
        "name": "Cloudflare",
        "headers": {"server": re.compile(r"cloudflare", re.I),
                    "cf-ray": re.compile(r"."),
                    "cf-cache-status": re.compile(r".")},
        "directive": "Slow scans, respect rate limits; try origin IP discovery; "
                     "payload obfuscation recommended",
    },
    {
        "name": "Akamai",
        "headers": {"server": re.compile(r"akamai|akamaighost", re.I),
                    "x-akamai-transformed": re.compile(r"."),
                    "x-akamai-origin-hop": re.compile(r".")},
        "directive": "Adaptive rate limiting in effect; fingerprint origin behind edge",
    },
    {
        "name": "Imperva / Incapsula / Radware",
        "headers": {"x-iinfo": re.compile(r"."),
                    "x-cdn": re.compile(r"imperva", re.I)},
        "directive": "Strong bot detection; use human-like pacing and residential egress",
    },
    {
        "name": "AWS WAF / CloudFront",
        "headers": {"x-amz-cf-id": re.compile(r"."),
                    "x-amz-cf-pop": re.compile(r"."),
                    "via": re.compile(r"cloudfront", re.I)},
        "directive": "AWS rate-based rules likely; rotate pacing; check for "
                     "X-Amzn-Waf-Action blocks",
    },
    {
        "name": "ModSecurity",
        "headers": {"server": re.compile(r"mod_security|modsecurity", re.I)},
        "directive": "OWASP CRS ruleset likely — obfuscate payloads "
                     "(case, comments, encoding)",
    },
    {
        "name": "Fastly",
        "headers": {"x-served-by": re.compile(r"cache-", re.I),
                    "via": re.compile(r"varnish|fastly", re.I)},
        "directive": "Edge rules possible; check Fastly shield POP behavior",
    },
    {
        "name": "Sucuri",
        "headers": {"server": re.compile(r"sucuri", re.I),
                    "x-sucuri-id": re.compile(r".")},
        "directive": "Sucuri CloudProxy — JS challenge on suspicious traffic",
    },
    {
        "name": "F5 BIG-IP",
        "headers": {"server": re.compile(r"bigip|f5", re.I),
                    "x-cnection": re.compile(r".")},
        "directive": "BIG-IP ASM — watch for TS cookies; normalize headers",
    },
    {
        "name": "Azure Front Door",
        "headers": {"x-azure-ref": re.compile(r"."),
                    "server": re.compile(r"azure", re.I)},
        "directive": "Azure WAF policy possible; check x-azure-ref correlation",
    },
    {
        "name": "Palo Alto / Fortinet",
        "headers": {"server": re.compile(r"panwebserver|fortigate", re.I)},
        "directive": "Network-level WAF; expect aggressive TCP-level blocking",
    },
]

WAF_BLOCK_STATUSES = {403, 406, 429, 501}


def detect_from_headers(
    headers: dict[str, str], status_code: int | None = None, body_snippet: str = ""
) -> dict[str, Any]:
    """Fingerprint a WAF/CDN purely from response evidence."""
    lower = {k.lower(): v for k, v in headers.items()}
    hits: list[dict[str, Any]] = []
    for signature in WAF_SIGNATURES:
        matched_headers = []
        for header, pattern in signature["headers"].items():
            if header in lower and pattern.search(lower.get(header, "")):
                matched_headers.append(f"{header}: {lower[header][:60]}")
        if matched_headers:
            hits.append(
                {
                    "waf": signature["name"],
                    "evidence": matched_headers,
                    "directive": signature["directive"],
                }
            )

    body_block_hints = []
    if body_snippet:
        for marker in ("Request blocked", "captcha-delivery.com", "Attention Required",
                       "Access Denied", "challenge-platform", "denied by security policy"):
            if marker.lower() in body_snippet.lower():
                body_block_hints.append(marker)

    return {
        "detected": bool(hits),
        "wafs": hits,
        "block_status": status_code in WAF_BLOCK_STATUSES if status_code else False,
        "body_block_hints": body_block_hints,
        "recommendation": (
            hits[0]["directive"] if hits else
            "No WAF fingerprinted from headers — proceed with standard pacing"
        ),
    }


def detect_with_wafw00f(url: str, timeout: int = 30) -> dict[str, Any] | None:
    """Run wafw00f if installed; returns parsed output or None.

    Runs in a worker thread so it never blocks or nests the MCP event loop.
    """
    if shutil.which("wafw00f") is None:
        return None

    import concurrent.futures
    import subprocess

    def _run_sync() -> str:
        try:
            proc = subprocess.run(
                ["wafw00f", "-a", url],
                capture_output=True,
                text=True,
                timeout=timeout,
                errors="replace",
            )
            return proc.stdout + proc.stderr
        except (subprocess.TimeoutExpired, OSError):
            return ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        output = pool.submit(_run_sync).result()

    if not output:
        return None
    result: dict[str, Any] = {"raw": output[:2000], "wafs": []}
    for match in re.finditer(r"is behind (.*?)\s*$", output, re.M):
        result["wafs"].append(match.group(1).strip())
    result["detected"] = bool(result["wafs"]) or "is behind" in output
    return result
