"""Navigation tools."""

from __future__ import annotations

import re

from fastmcp.exceptions import ToolError

from ._base import maybe_snapshot, page_for

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")

# Schemes that are valid without a "//" authority component. Anything else
# without a scheme gets https:// prepended (so "example.com:8080" still works).
_BARE_SCHEMES = {
    "about",
    "blob",
    "chrome",
    "data",
    "devtools",
    "javascript",
    "mailto",
    "view-source",
    "ws",
    "wss",
}


def _sanitize_url(url: str) -> str:
    url = (url or "").strip().strip('"').strip("'")
    if not url:
        raise ToolError("url is required")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        return url
    m = _SCHEME_RE.match(url)
    if m and m.group(1).lower() in _BARE_SCHEMES:
        return url
    return f"https://{url}"


async def browser_navigate(
    url: str,
    session: str = "default",
    tab: int | None = None,
    wait: str = "domcontentloaded",
) -> str:
    """Navigate the active (or specified) tab to a URL.

    Returns the new page state; includes a fresh snapshot when the page
    content changed (configurable via NAVIGATOR_AUTO_SNAPSHOT).
    """
    runtime, sess, ps = await page_for(session, tab)
    target = _sanitize_url(url)
    runtime.scope_guard(target)
    try:
        await ps.page.goto(target, wait_until=wait)
    except Exception as exc:
        raise ToolError(f"Navigation failed: {exc}") from exc
    runtime.meter.record("browser_navigate", navigation=True)
    ps.last_snapshot_hash = ""  # new document — invalidate cache
    snap = await maybe_snapshot(ps) if runtime.settings.auto_snapshot_on_change else ""
    result = f"Navigated to {ps.page.url}\nTitle: {await ps.page.title()}"
    if snap:
        result += "\n\n" + snap
    return result


async def browser_navigate_back(session: str = "default", tab: int | None = None) -> str:
    """Go back one history step in the tab."""
    runtime, _, ps = await page_for(session, tab)
    try:
        await ps.page.go_back(wait_until="domcontentloaded")
    except Exception as exc:
        raise ToolError(f"Back navigation failed: {exc}") from exc
    ps.last_snapshot_hash = ""
    return f"Went back. Now at: {ps.page.url}"


async def browser_navigate_forward(session: str = "default", tab: int | None = None) -> str:
    """Go forward one history step in the tab."""
    runtime, _, ps = await page_for(session, tab)
    try:
        await ps.page.go_forward(wait_until="domcontentloaded")
    except Exception as exc:
        raise ToolError(f"Forward navigation failed: {exc}") from exc
    ps.last_snapshot_hash = ""
    return f"Went forward. Now at: {ps.page.url}"


async def browser_reload(session: str = "default", tab: int | None = None) -> str:
    """Reload the current page."""
    runtime, _, ps = await page_for(session, tab)
    try:
        await ps.page.reload(wait_until="domcontentloaded")
    except Exception as exc:
        raise ToolError(f"Reload failed: {exc}") from exc
    ps.last_snapshot_hash = ""
    snap = await maybe_snapshot(ps) if runtime.settings.auto_snapshot_on_change else ""
    result = f"Reloaded {ps.page.url}"
    if snap:
        result += "\n\n" + snap
    return result


async def browser_wait_for(
    text: str | None = None,
    selector: str | None = None,
    time_s: float | None = None,
    session: str = "default",
    tab: int | None = None,
    timeout_ms: int = 8000,
) -> str:
    """Wait until text appears, a selector matches, or a fixed time passes."""
    runtime, _, ps = await page_for(session, tab)
    page = ps.page
    try:
        if text is not None:
            await page.wait_for_selector(f"text={text}", timeout=timeout_ms)
            return f"Text {text!r} appeared."
        if selector is not None:
            await page.wait_for_selector(selector, timeout=timeout_ms)
            return f"Selector {selector!r} appeared."
        if time_s is not None:
            import asyncio

            await asyncio.sleep(min(time_s, 60))
            return f"Waited {time_s}s."
    except Exception as exc:
        raise ToolError(f"Wait condition not met: {exc}") from exc
    raise ToolError("Provide one of: text, selector, or time_s")


async def browser_get_url(session: str = "default", tab: int | None = None) -> str:
    """Return the current URL and title of the tab."""
    runtime, _, ps = await page_for(session, tab)
    return f"URL: {ps.page.url}\nTitle: {await ps.page.title()}"
