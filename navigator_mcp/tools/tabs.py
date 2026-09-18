"""Tab management tools."""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from ._base import json_safe, rt


def _get_session(runtime, session: str):
    sess = runtime.browser.sessions.get(session)
    if sess is None:
        raise ToolError(
            f"session '{session}' not found. Active sessions: "
            f"{sorted(runtime.browser.sessions) or 'none'}."
        )
    return sess


async def browser_tab_list(session: str = "default") -> str:
    """List the tabs of a session with their URLs."""
    runtime = rt()
    sess = _get_session(runtime, session)
    tabs = [
        {"index": i, "url": ps.page.url, "active": i == sess.active_index}
        for i, ps in enumerate(sess.pages)
    ]
    return json_safe({"session": session, "tabs": tabs})


async def browser_tab_new(
    url: str | None = None, session: str = "default"
) -> str:
    """Open a new tab (optionally navigating it to a URL) and make it active."""
    runtime = rt()
    if url:
        runtime.scope_guard(url)
    if session not in runtime.browser.sessions:
        if session == "default":
            await runtime.browser.ensure_session("default")
        else:
            _get_session(runtime, session)  # raises a clean error
    try:
        ps = await runtime.browser.new_tab(session, url)
        sess = runtime.browser.get_session(session)
    except Exception as exc:
        raise ToolError(str(exc)) from exc
    runtime.meter.record("browser_tab_new")
    return json_safe(
        {"tab_index": len(sess.pages) - 1,
         "url": ps.page.url,
         "note": "New tab is now active for this session."}
    )


async def browser_tab_select(
    index: int, session: str = "default"
) -> str:
    """Make another tab active (subsequent tools act on it)."""
    runtime = rt()
    sess = _get_session(runtime, session)
    if not 0 <= index < len(sess.pages):
        raise ToolError(f"tab index {index} out of range (0..{len(sess.pages) - 1})")
    sess.active_index = index
    runtime.meter.record("browser_tab_select")
    return f"Active tab is now {index}: {sess.pages[index].page.url}"


async def browser_tab_close(index: int, session: str = "default") -> str:
    """Close a tab (the active one cannot be the last tab)."""
    runtime = rt()
    sess = _get_session(runtime, session)
    try:
        await runtime.browser.close_tab(session, index)
    except (ValueError, IndexError) as exc:
        raise ToolError(str(exc)) from exc
    runtime.meter.record("browser_tab_close")
    return f"Closed tab {index}. {len(sess.pages)} tab(s) remain; active is {sess.active_index}."
