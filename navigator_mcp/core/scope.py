"""Optional navigation lockdown (policy scope).

Set ``NAVIGATOR_ALLOWED_DOMAINS`` (comma-separated, wildcards allowed) to pin the
browser to an allowlist of domains — useful for keeping an autonomous agent
on-task. When unset (default), all navigation is allowed.

Host matching: an exact pattern (``example.com``) also matches its subdomains;
``*.example.com`` is accepted and behaves identically.

(The former *engagement* scope layer — subdomain-inclusive scopes set before
security testing — moved to ``reference/`` with the rest of the security
suite, pending the dedicated Security MCP.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


def _normalize_host(host: str) -> str:
    return (host or "").strip().lower().rstrip(".")


def host_matches(pattern: str, host: str) -> bool:
    """Check a host against an exact or wildcard (``*.domain``) pattern.

    An exact pattern (``example.com``) also matches its subdomains
    (``api.example.com``). A ``*.example.com`` pattern is accepted and
    behaves identically.
    """
    pattern = _normalize_host(pattern)
    host = _normalize_host(host)
    if not pattern or not host:
        return False
    if pattern.startswith("*."):
        pattern = pattern[2:]
    return pattern == host or host.endswith("." + pattern)


@dataclass
class ScopeManager:
    """Policy-scope enforcement for browser navigation."""

    policy_hosts: set[str] = field(default_factory=set)

    # ------------------------------------------------------------------ policy

    def set_policy(self, domains: list[str]) -> None:
        self.policy_hosts = {_normalize_host(d) for d in domains if d.strip()}

    # ------------------------------------------------------------------ checks

    def check(self, url: str) -> tuple[bool, str]:
        """Returns ``(allowed, reason_if_denied)``."""
        if not self.policy_hosts:
            return True, ""
        try:
            host = urlparse(url).hostname or ""
        except (ValueError, AttributeError):
            return False, f"policy: unparseable URL {url!r}"
        if not host:
            return False, f"policy: URL has no host {url!r}"
        for pattern in self.policy_hosts:
            if host_matches(pattern, host):
                return True, ""
        return False, (
            f"policy: host '{host}' is not in the allowed domains "
            f"({', '.join(sorted(self.policy_hosts))})"
        )

    def status(self) -> dict:
        return {
            "allowed_domains": sorted(self.policy_hosts),
            "lockdown_active": bool(self.policy_hosts),
        }
