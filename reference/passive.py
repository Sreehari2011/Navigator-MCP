"""Passive security scanner — never sends a payload, only reads what the page
and server already expose.

Three scanners (mirroring the Hypervisor ``PassiveScanner`` interface):
  * ``scan_headers`` — missing security headers, cookie flag issues, info leaks
  * ``scan_text``    — secrets, internal IPs, stack traces, SQL errors
  * ``scan_urls``    — mixed content, exposed files, API surface hints

Every alert is a formatted, LLM-actionable string. Rules are tuned to keep
false positives low (minimum-entropy checks on secret-like tokens).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# ---------------------------------------------------------------------------
# Header rules
# ---------------------------------------------------------------------------

SECURITY_HEADERS = {
    "content-security-policy": (
        "MISCONFIG: Content-Security-Policy header missing — XSS risk is unmitigated"
    ),
    "strict-transport-security": (
        "MISCONFIG: Strict-Transport-Security (HSTS) missing — protocol downgrade possible"
    ),
    "x-content-type-options": (
        "MISCONFIG: X-Content-Type-Options missing — MIME sniffing attacks possible"
    ),
    "referrer-policy": (
        "MISCONFIG: Referrer-Policy missing — URL data may leak to third parties"
    ),
    "permissions-policy": (
        "INFO: Permissions-Policy header missing — browser features unrestricted"
    ),
}

VERSION_LEAK_HEADERS = {
    "server": re.compile(r"\d+\.\d+", re.I),
    "x-powered-by": re.compile(r".", re.I),
    "x-aspnet-version": re.compile(r".", re.I),
    "x-aspnetmvc-version": re.compile(r".", re.I),
    "x-runtime": re.compile(r".", re.I),
    "x-generator": re.compile(r".", re.I),
    "x-drupal-cache": re.compile(r".", re.I),
}

FRAME_PROTECTION = {"x-frame-options", "content-security-policy"}


def scan_headers(headers: dict[str, str] | Iterable[tuple[str, str]]) -> list[str]:
    """Analyze response headers for missing protections and info leaks."""
    if not isinstance(headers, dict):
        headers = dict(headers)
    lower = {k.lower(): v for k, v in headers.items()}
    alerts: list[str] = []

    for header, message in SECURITY_HEADERS.items():
        if header not in lower:
            alerts.append(message)

    if not any(h in lower for h in FRAME_PROTECTION):
        alerts.append(
            "MISCONFIG: No clickjacking protection (X-Frame-Options / CSP frame-ancestors)"
        )

    for header, pattern in VERSION_LEAK_HEADERS.items():
        if header in lower and pattern.search(lower.get(header, "")):
            value = lower.get(header, "")[:60]
            alerts.append(f"INFO-LEAK: {header}: {value!r} discloses technology/version")

    # cookie flags
    set_cookies: list[str] = []
    for k, v in headers.items():
        if k.lower() == "set-cookie":
            set_cookies.append(v if isinstance(v, str) else str(v))
    for cookie in set_cookies:
        name = cookie.split("=", 1)[0][:40]
        flags = cookie.lower()
        issues = []
        if "secure" not in flags:
            issues.append("not Secure")
        if "httponly" not in flags:
            issues.append("not HttpOnly")
        if "samesite" not in flags:
            issues.append("no SameSite")
        if issues:
            alerts.append(
                f"MISCONFIG: cookie {name!r} set without: {', '.join(issues)}"
            )

    acao = lower.get("access-control-allow-origin", "")
    if acao == "*":
        alerts.append(
            "MISCONFIG: Access-Control-Allow-Origin: * — any origin can read responses"
        )

    return alerts


# ---------------------------------------------------------------------------
# Text rules (secrets & error leakage)
# ---------------------------------------------------------------------------

def _has_entropy(token: str, minimum: float = 3.0) -> bool:
    """Cheap Shannon-entropy estimate to suppress obvious false positives."""
    if not token:
        return False
    freq: dict[str, int] = {}
    for ch in token:
        freq[ch] = freq.get(ch, 0) + 1
    import math

    entropy = -sum((c / len(token)) * math.log2(c / len(token)) for c in freq.values())
    return entropy >= minimum


SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Stripe secret key", re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{24,}\b")),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("Mailgun key", re.compile(r"\bkey-[0-9a-zA-Z]{32}\b")),
    ("NPM token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
]

LEAK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Internal IP address", re.compile(
        r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    )),
    ("SQL error message", re.compile(
        r"(SQL syntax|Warning: mysql_|unterminated quoted string|"
        r"ORA-\d{4,5}|PostgreSQL.{0,30}ERROR|SQLite3?::query|Unclosed quotation mark)"
    )),
    ("Stack trace / debug output", re.compile(
        r"(Traceback \(most recent call last\)|at [\w$.]+\(.*?:\d+:\d+\)"
        r"|System\.NullReferenceException|java\.lang\.Exception)"
    )),
    ("Email address exposure", re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )),
]


def scan_text(text: str, *, include_emails: bool = False) -> list[str]:
    """Scan page text / console logs / JS for secrets and leakage."""
    alerts: list[str] = []
    if not text:
        return alerts

    seen: set[str] = set()
    for label, pattern in SECRET_PATTERNS:
        for match in pattern.findall(text):
            token = match if isinstance(match, str) else match[0]
            key = f"{label}:{token[:12]}"
            if key in seen or not _has_entropy(token, 2.5):
                continue
            seen.add(key)
            preview = token[:10] + "…" + token[-4:] if len(token) > 18 else token
            alerts.append(
                f"SECRET: Possible {label} exposed: {preview} "
                f"(verify before reporting — could be a public test key)"
            )

    for label, pattern in LEAK_PATTERNS:
        if label == "Email address exposure" and not include_emails:
            continue
        matches = pattern.findall(text)
        unique = list(dict.fromkeys([m if isinstance(m, str) else m[0] for m in matches]))
        if unique:
            preview = ", ".join(str(u) for u in unique[:4])
            alerts.append(f"LEAK: {label} found in page content: {preview[:120]}")

    return alerts


# ---------------------------------------------------------------------------
# URL rules
# ---------------------------------------------------------------------------

URL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Mixed content (http:// resource on https page)", re.compile(r"^http://")),
    ("Exposed source-control artifact", re.compile(r"\.git(/|$)")),
    ("Exposed environment file", re.compile(r"\.env($|\.)")),
    ("Backup / dump file", re.compile(
        r"\.(bak|backup|sql|dump|old|orig|swp)(\?|$)", re.I
    )),
    ("API documentation endpoint", re.compile(
        r"/(swagger|api-docs|openapi\.json|graphql)(/|$|\.)", re.I
    )),
    ("Admin interface", re.compile(r"/(admin|wp-admin|manager-html)(/|$)", re.I)),
    ("Cloud metadata-style endpoint", re.compile(
        r"(169\.254\.169\.254|metadata\.google\.internal)"
    )),
    ("S3 bucket URL", re.compile(r"https?://[a-z0-9.-]+\.s3\.amazonaws\.com", re.I)),
    ("Firebase endpoint", re.compile(r"https?://[a-z0-9-]+\.firebaseio\.com", re.I)),
]


def scan_urls(urls: Iterable[str], *, page_is_https: bool = True) -> list[str]:
    """Scan discovered resource/API URLs for exposure signals."""
    alerts: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not url or not isinstance(url, str):
            continue
        for label, pattern in URL_PATTERNS:
            if label.startswith("Mixed") and not page_is_https:
                continue
            if pattern.search(url):
                key = f"{label}:{url[:60]}"
                if key in seen:
                    continue
                seen.add(key)
                alerts.append(f"EXPOSURE: {label}: {url[:140]}")
    return alerts


# ---------------------------------------------------------------------------
# Combined convenience
# ---------------------------------------------------------------------------

def scan_page(
    *, headers: dict[str, str], text: str, urls: list[str], page_is_https: bool = True
) -> list[str]:
    """Run all three scanners and return a deduplicated alert list."""
    alerts = scan_headers(headers)
    alerts.extend(scan_text(text))
    alerts.extend(scan_urls(urls, page_is_https=page_is_https))
    return list(dict.fromkeys(alerts))
