"""Network observation & control tools."""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from ..network.interceptor import apply_capture_filter, discover_apis
from ._base import json_safe, page_for, rt


async def browser_network_capture_start(
    session: str = "default",
    tab: int | None = None,
    resource_types: list[str] | None = None,
    url_contains: str | None = None,
    methods: list[str] | None = None,
    clear: bool = True,
) -> str:
    """Start recording network requests on this tab.

    Optional filters: resource_types (document/xhr/fetch/script/image/...),
    url_contains (substring), methods (GET/POST/...). Default records everything."""
    runtime, _, ps = await page_for(session, tab)
    ps.network_capture = True
    apply_capture_filter(ps, resource_types, url_contains, methods)
    if clear:
        ps.requests.clear()
    runtime.meter.record("browser_network_capture_start")
    return (
        f"Network capture ON for tab (filters: types={resource_types or 'all'}, "
        f"url~{url_contains or 'any'}, methods={methods or 'all'}). "
        f"Use browser_network_list() to read, browser_network_capture_stop() to stop."
    )


async def browser_network_capture_stop(
    session: str = "default", tab: int | None = None
) -> str:
    """Stop recording network requests (buffer is kept until next start)."""
    runtime, _, ps = await page_for(session, tab)
    ps.network_capture = False
    runtime.meter.record("browser_network_capture_stop")
    return f"Network capture OFF. {len(ps.requests)} requests remain in the buffer."


async def browser_network_list(
    n: int = 30,
    statuses: list[int] | None = None,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """List captured network requests (most recent first)."""
    runtime, _, ps = await page_for(session, tab)
    entries = ps.network_list(n=n, statuses=statuses)
    runtime.meter.record("browser_network_list")
    if not entries:
        return "No captured requests. Start capture with browser_network_capture_start()."
    return json_safe({"count": len(entries), "requests": entries})


async def browser_network_get(
    index: int, session: str = "default", tab: int | None = None
) -> str:
    """Fetch full details + response body of a captured request (by index)."""
    runtime, _, ps = await page_for(session, tab)
    data = await ps.network_body(index)
    runtime.meter.record("browser_network_get")
    return json_safe(data, max_chars=24000)


async def browser_network_block(url_globs: list[str]) -> str:
    """Block requests matching URL globs across all sessions.

    Examples: ["**/*.css", "**/ads.js", "*doubleclick*"]. Blocks ads and
    trackers to speed up automation dramatically."""
    runtime = rt()
    if not url_globs:
        raise ToolError("url_globs must be a non-empty list")
    await runtime.browser.block_urls(url_globs)
    runtime.meter.record("browser_network_block")
    return f"Blocking {len(url_globs)} pattern(s): {url_globs}"


async def browser_network_unblock() -> str:
    """Remove all URL blocking rules."""
    runtime = rt()
    await runtime.browser.clear_blocked_urls()
    runtime.meter.record("browser_network_unblock")
    return "All blocking rules removed."


async def browser_discover_apis(
    session: str = "default", tab: int | None = None, limit: int = 40
) -> str:
    """Discover background API endpoints (fetch/XHR) used by the page —
    including internal/undocumented APIs, from capture or live observation."""
    runtime, _, ps = await page_for(session, tab)
    data = await discover_apis(ps.page, ps, limit=limit)
    runtime.meter.record("browser_discover_apis")
    return json_safe(data)


async def browser_set_dialog_mode(
    mode: str, session: str = "default", tab: int | None = None
) -> str:
    """Set dialog handling: "auto" (accept + record — default) or "manual"
    (pause dialogs so browser_dialog_respond can answer them)."""
    runtime, _, ps = await page_for(session, tab)
    if mode not in {"auto", "manual"}:
        raise ToolError("mode must be 'auto' or 'manual'")
    ps.dialog_mode = mode
    return f"Dialog mode set to '{mode}'."


async def browser_dialog_respond(
    accept: bool = True,
    text: str = "",
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Respond to a pending manual-mode dialog (accept/dismiss, optional text)."""
    runtime, _, ps = await page_for(session, tab)
    if ps.pending_dialog is None:
        return "No pending dialog on this tab."
    dialog = ps.pending_dialog
    ps.pending_dialog = None
    try:
        if accept:
            await dialog.accept(text=text) if text else await dialog.accept()
        else:
            await dialog.dismiss()
    except Exception as exc:
        raise ToolError(f"Dialog respond failed: {exc}") from exc
    outcome = "accepted" if accept else "dismissed"
    return f"Dialog {outcome}" + (f" with text {text!r}" if text else "")
