"""Session (isolated browser context) management tools.

Sessions are the isolation unit: separate cookies, storage, fingerprint and
proxy. Persist auth with save_auth + restore with the ``profile`` argument
of browser_session_new.
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from ._base import json_safe, rt


async def browser_session_list() -> str:
    """List all active sessions with their tabs, fingerprints and proxies."""
    runtime = rt()
    return json_safe({"sessions": runtime.browser.session_infos()})


async def browser_session_new(
    name: str,
    stealth: bool = True,
    profile: str | None = None,
    proxy: str | None = None,
    fingerprint: str | None = None,
    locale: str | None = None,
    timezone: str | None = None,
    geolocation: dict | None = None,
    bypass_csp: bool = False,
    record_har: str | None = None,
) -> str:
    """Create a new isolated browser session.

    - stealth: apply anti-detection fingerprinting (default on)
    - profile: restore a saved auth profile (from browser_session_save_auth)
    - proxy: per-session proxy server (e.g. http://user:pass@host:port)
    - fingerprint: specific fingerprint name (see stealth docs), random by default
    - bypass_csp: disable CSP enforcement (for pages that block inline scripts)
    - record_har: file path to record a HAR archive of all traffic
    """
    runtime = rt()
    if name in runtime.browser.sessions:
        raise ToolError(f"Session '{name}' already exists")
    runtime.check_session_budget()
    storage_state = None
    if profile:
        storage_state = runtime.browser.storage_path_for(profile)
        import os

        if not os.path.isfile(storage_state):
            raise ToolError(f"Profile '{profile}' not found at {storage_state}")
    try:
        sess = await runtime.browser.create_session(
            name,
            stealth=stealth,
            proxy=proxy,
            storage_state=storage_state,
            fingerprint_name=fingerprint,
            locale=locale,
            timezone=timezone,
            geolocation=geolocation,
            bypass_csp=bypass_csp,
            record_har=record_har,
        )
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        raise ToolError(f"Session creation failed: {exc}") from exc
    runtime.meter.record("browser_session_new")
    return json_safe(sess.info())


async def browser_session_close(name: str) -> str:
    """Close a session and all its tabs (cookies/storage are discarded
    unless saved with browser_session_save_auth)."""
    runtime = rt()
    try:
        await runtime.browser.close_session(name)
    except KeyError as exc:
        raise ToolError(str(exc)) from exc
    runtime.meter.record("browser_session_close")
    return f"Session '{name}' closed. Active sessions: {sorted(runtime.browser.sessions) or 'none'}"


async def browser_session_save_auth(
    name: str, profile_name: str
) -> str:
    """Persist the session's cookies + localStorage to a named profile.

    Restore later via browser_session_new(profile=profile_name) — survives
    restarts, perfect for staying logged in across engagements."""
    runtime = rt()
    try:
        path = await runtime.browser.save_auth(name, profile_name)
    except KeyError as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        raise ToolError(f"Saving auth state failed: {exc}") from exc
    runtime.meter.record("browser_session_save_auth")
    return f"Auth state for session '{name}' saved to profile '{profile_name}' ({path})."
