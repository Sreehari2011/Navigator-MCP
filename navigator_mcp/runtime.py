"""Process-wide runtime wiring: settings + browser + local stats.

A single :class:`NavigatorRuntime` instance is created lazily and shared by every
tool invocation. The FastMCP lifespan starts/stops it.

No licensing, no gating: every Navigator capability is always available.
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from .config import Settings, get_settings
from .core.browser import BrowserRuntime
from .core.scope import ScopeManager
from .metering import UsageMeter


class NavigatorRuntime:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.meter = UsageMeter(self.settings.usage_file, self.settings.metering_enabled)
        self.scope = ScopeManager()
        self.scope.set_policy(self.settings.allowed_domains)
        self.browser = BrowserRuntime(self.settings)

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        await self.browser.start()

    async def stop(self) -> None:
        await self.browser.stop()

    # ------------------------------------------------------------------ resource sanity

    def check_session_budget(self, additional: int = 1) -> None:
        """Resource guard — never a licensing limit. Raise if creating another
        session would exceed NAVIGATOR_MAX_SESSIONS (default 64)."""
        current = len(self.browser.sessions)
        cap = self.settings.max_sessions
        if current + additional > cap:
            raise ToolError(
                f"Session cap reached ({cap} — configurable via NAVIGATOR_MAX_SESSIONS). "
                f"Close a session with browser_session_close() first."
            )

    # ------------------------------------------------------------------ navigation lockdown

    def scope_guard(self, url: str) -> None:
        """Enforce the optional NAVIGATOR_ALLOWED_DOMAINS navigation allowlist."""
        ok, reason = self.scope.check(url)
        if not ok:
            raise ToolError(f"NAVIGATION BLOCKED: {reason}")


_runtime: NavigatorRuntime | None = None


def get_runtime() -> NavigatorRuntime:
    global _runtime
    if _runtime is None:
        _runtime = NavigatorRuntime()
    return _runtime


def reset_runtime() -> None:
    """Test helper — drops the singleton (does not stop browsers)."""
    global _runtime
    _runtime = None
