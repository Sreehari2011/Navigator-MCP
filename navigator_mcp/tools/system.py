"""System/status tools."""

from __future__ import annotations

from .. import __version__
from ._base import json_safe, rt


async def navigator_status() -> str:
    """One-call status: version, sessions, scope, providers, limits."""
    runtime = rt()
    return json_safe({
        "name": "Navigator MCP",
        "version": __version__,
        "features": "all unlocked (no licensing, no gating)",
        "sessions": runtime.browser.session_infos(),
        "max_sessions": runtime.settings.max_sessions,
        "navigation_lockdown": runtime.scope.status(),
        "captcha_providers": {
            "2captcha": bool(runtime.settings.twocaptcha_api_key),
            "capsolver": bool(runtime.settings.capsolver_api_key),
        },
        "stealth": runtime.settings.stealth,
        "humanize": runtime.settings.humanize_input,
    })


async def usage_report() -> str:
    """Local usage stats: tool call counts, per-day breakdown, totals.

    Purely local counters (~/.navigator/usage.json) for your own insight — no URLs
    or page content are ever recorded. Disable with NAVIGATOR_STATS=false."""
    runtime = rt()
    return json_safe(runtime.meter.report())
