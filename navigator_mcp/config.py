"""Central configuration for Navigator MCP.

All settings are environment-variable driven so the same build can run locally
(stdio, Claude Desktop / Cursor / VS Code) or in a container (HTTP, multi-key).
Nothing here phones home — there is no license server, no telemetry, no
phone-home of any kind. Every feature is always unlocked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _default_workspace() -> Path:
    override = os.environ.get("NAVIGATOR_WORKSPACE")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".navigator").resolve()


@dataclass
class Settings:
    """Runtime settings, resolved once at startup."""

    # ------------------------------------------------------------------ paths
    workspace_dir: Path = field(default_factory=_default_workspace)
    profiles_dir: Path = field(init=False)
    downloads_dir: Path = field(init=False)
    usage_file: Path = field(init=False)

    # ------------------------------------------------------------------ browser
    headless: bool = field(default_factory=lambda: _env_bool("NAVIGATOR_HEADLESS", True))
    browser_channel: str = field(
        default_factory=lambda: os.environ.get("NAVIGATOR_BROWSER_CHANNEL", "chromium")
    )
    default_viewport_width: int = field(
        default_factory=lambda: _env_int("NAVIGATOR_VIEWPORT_WIDTH", 1440)
    )
    default_viewport_height: int = field(
        default_factory=lambda: _env_int("NAVIGATOR_VIEWPORT_HEIGHT", 900)
    )
    navigation_timeout_ms: int = field(
        default_factory=lambda: _env_int("NAVIGATOR_NAV_TIMEOUT_MS", 30000)
    )
    action_timeout_ms: int = field(
        default_factory=lambda: _env_int("NAVIGATOR_ACTION_TIMEOUT_MS", 10000)
    )
    settle_delay_ms: int = field(
        default_factory=lambda: _env_int("NAVIGATOR_SETTLE_DELAY_MS", 350)
    )
    # Connect to an already-running (possibly patched/anti-detect) browser
    # instead of launching one, e.g. ws://127.0.0.1:9222/playwright
    cdp_endpoint: str = field(
        default_factory=lambda: os.environ.get("NAVIGATOR_CDP_ENDPOINT", "")
    )
    proxy_server: str = field(
        default_factory=lambda: os.environ.get("NAVIGATOR_PROXY_SERVER", "")
    )
    # Resource sanity cap (not a licensing limit): how many parallel isolated
    # browser sessions may exist at once. Raise it if your machine can cope.
    max_sessions: int = field(
        default_factory=lambda: _env_int("NAVIGATOR_MAX_SESSIONS", 64)
    )

    # ------------------------------------------------------------------ stealth
    stealth: bool = field(default_factory=lambda: _env_bool("NAVIGATOR_STEALTH", True))
    humanize_input: bool = field(
        default_factory=lambda: _env_bool("NAVIGATOR_HUMANIZE", True)
    )

    # ------------------------------------------------------------------ captcha
    twocaptcha_api_key: str = field(
        default_factory=lambda: os.environ.get("TWOCAPTCHA_API_KEY", "")
    )
    capsolver_api_key: str = field(
        default_factory=lambda: os.environ.get("CAPSOLVER_API_KEY", "")
    )
    captcha_poll_interval_s: float = 5.0
    captcha_manual_timeout_s: int = field(
        default_factory=lambda: _env_int("NAVIGATOR_CAPTCHA_MANUAL_TIMEOUT_S", 300)
    )

    # ------------------------------------------------------------------ navigation lockdown
    # Optional domain allowlist for the browser (keep agents on-task).
    # Unset = all navigation allowed.
    allowed_domains: list[str] = field(
        default_factory=lambda: _env_list("NAVIGATOR_ALLOWED_DOMAINS")
    )

    # ------------------------------------------------------------------ remote access (optional)
    # Set NAVIGATOR_API_KEYS to require bearer keys when exposing the HTTP transport
    # (e.g. a home server reachable from your laptop). Purely opt-in security.
    api_keys: list[str] = field(
        default_factory=lambda: _env_list("NAVIGATOR_API_KEYS")
    )
    http_host: str = field(
        default_factory=lambda: os.environ.get("NAVIGATOR_HTTP_HOST", "127.0.0.1")
    )
    http_port: int = field(default_factory=lambda: _env_int("NAVIGATOR_HTTP_PORT", 8765))

    # ------------------------------------------------------------------ local usage stats
    # Purely local counters (~/.navigator/usage.json) so you can see your own usage
    # via the usage_report tool. No URLs or page content are ever recorded.
    metering_enabled: bool = field(
        default_factory=lambda: _env_bool("NAVIGATOR_STATS", True)
    )

    # ------------------------------------------------------------------ snapshot
    max_snapshot_nodes: int = field(
        default_factory=lambda: _env_int("NAVIGATOR_MAX_SNAPSHOT_NODES", 400)
    )
    auto_snapshot_on_change: bool = field(
        default_factory=lambda: _env_bool("NAVIGATOR_AUTO_SNAPSHOT", True)
    )

    def __post_init__(self) -> None:
        self.workspace_dir = Path(self.workspace_dir)
        self.profiles_dir = self.workspace_dir / "profiles"
        self.downloads_dir = self.workspace_dir / "downloads"
        self.usage_file = self.workspace_dir / "usage.json"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings singleton (lazily built)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset cached settings (used by tests)."""
    global _settings
    _settings = None
