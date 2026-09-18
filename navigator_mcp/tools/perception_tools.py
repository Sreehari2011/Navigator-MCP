"""Perception tools: snapshots, search, extraction."""

from __future__ import annotations

import re

from fastmcp.exceptions import ToolError

from ..perception import extraction as ex
from ..perception import snapshot as snap
from ._base import json_safe, page_for


async def browser_snapshot(
    session: str = "default",
    tab: int | None = None,
    force: bool = False,
    deep: bool = False,
) -> str:
    """Capture the page as a compact, ref-annotated accessibility snapshot.

    Elements get stable refs (e.g. [ref=e12]) that interaction tools accept.
    If the page is unchanged since the last snapshot, returns a short
    "unchanged" notice instead of re-sending the tree (major token savings).
    Set force=true to always re-render, deep=true to include child frames.
    """
    runtime, _, ps = await page_for(session, tab)
    try:
        if deep:
            raw = await snap.capture_deep(ps.page, runtime.settings.max_snapshot_nodes)
            text = snap.render_deep(raw)
            h = snap.snapshot_hash(raw)
        else:
            raw = await snap.capture(ps.page, runtime.settings.max_snapshot_nodes)
            h = snap.snapshot_hash(raw)
            if h == ps.last_snapshot_hash and not force:
                return (
                    f"Page unchanged since last snapshot (hash {h}). "
                    f"Use browser_snapshot(force=true) to re-render, or "
                    f"browser_find() to search elements."
                )
            text = snap.render_snapshot(raw)
    except Exception as exc:
        raise ToolError(f"Snapshot failed: {exc}") from exc

    ps.last_snapshot_hash = h
    ps.last_snapshot_text = text
    ps.snapshot_count += 1
    runtime.meter.record("browser_snapshot", snapshot_chars=len(text))
    return text


async def browser_find(
    pattern: str,
    role: str | None = None,
    session: str = "default",
    tab: int | None = None,
    limit: int = 20,
    include_structural: bool = False,
) -> str:
    """Search the current page for elements matching a text pattern (regex ok)
    and/or an ARIA role. Returns matching elements with their refs — cheaper
    than a full snapshot when you know what you're looking for.

    By default only actionable elements (links, buttons, fields, headings,
    images) are searched; set include_structural=true to also match
    containers (banner/navigation/form/...)."""
    runtime, _, ps = await page_for(session, tab)
    try:
        regex = re.compile(pattern, re.I)
    except re.error as exc:
        raise ToolError(f"Invalid regex {pattern!r}: {exc}") from exc
    try:
        raw = await snap.capture(ps.page, runtime.settings.max_snapshot_nodes)
    except Exception as exc:
        raise ToolError(f"Find failed: {exc}") from exc

    interactive = {
        "link", "button", "textbox", "searchbox", "combobox", "checkbox",
        "radio", "switch", "slider", "spinbutton", "option", "tab", "menuitem",
        "treeitem", "listbox", "heading", "image", "video", "audio",
    }
    matches = []
    for node in raw.get("nodes", []):
        node_role = node.get("role", "")
        is_actionable = node_role in interactive
        if not include_structural and not is_actionable:
            continue
        if role and node_role != role:
            continue
        name = node.get("name", "")
        if regex.search(name) or (not role and is_actionable and regex.search(node_role)):
            matches.append(
                f"- {node_role} \"{name}\" "
                f"[{' '.join(node.get('states', []))}] [ref={node['ref']}]"
            )
        if len(matches) >= limit:
            break
    runtime.meter.record("browser_find")
    if not matches:
        return (
            f"No elements matching /{pattern}/"
            + (f" role={role}" if role else "")
            + (
                " (structural containers excluded — retry with "
                "include_structural=true if you meant a container)"
                if not include_structural
                else ""
            )
        )
    return f"Found {len(matches)} match(es):\n" + "\n".join(matches)


async def browser_extract_text(
    ref: str | None = None,
    offset: int = 0,
    limit: int = 12000,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Extract text — whole page (smart main-content) or a specific element.

    Supports pagination via offset/limit for very long pages."""
    runtime, _, ps = await page_for(session, tab)
    try:
        data = await ex.extract_text(ps.page, ref, offset=offset, limit=limit)
    except Exception as exc:
        raise ToolError(f"Text extraction failed: {exc}") from exc
    runtime.meter.record("browser_extract_text")
    return json_safe(data, max_chars=limit + 800)


async def browser_extract_html(
    ref: str | None = None,
    offset: int = 0,
    limit: int = 20000,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Extract HTML — whole document or a specific element (by ref)."""
    runtime, _, ps = await page_for(session, tab)
    try:
        data = await ex.extract_html(ps.page, ref, offset=offset, limit=limit)
    except Exception as exc:
        raise ToolError(f"HTML extraction failed: {exc}") from exc
    runtime.meter.record("browser_extract_html")
    return json_safe(data, max_chars=limit + 800)


async def browser_extract_links(
    limit: int = 100, session: str = "default", tab: int | None = None
) -> str:
    """List all links (deduplicated) with their resolved hrefs."""
    runtime, _, ps = await page_for(session, tab)
    data = await ex.extract_links(ps.page, limit=limit)
    runtime.meter.record("browser_extract_links")
    return json_safe(data)


async def browser_extract_forms(
    session: str = "default", tab: int | None = None
) -> str:
    """List forms and their fields — the map for browser_fill_form."""
    runtime, _, ps = await page_for(session, tab)
    data = await ex.extract_forms(ps.page)
    runtime.meter.record("browser_extract_forms")
    return json_safe(data)


async def browser_extract_tables(
    limit_rows: int = 50, session: str = "default", tab: int | None = None
) -> str:
    """Extract <table> content as row arrays (token-cheap vs HTML)."""
    runtime, _, ps = await page_for(session, tab)
    data = await ex.extract_tables(ps.page, limit_rows=limit_rows)
    runtime.meter.record("browser_extract_tables")
    return json_safe(data)


async def browser_extract_meta(
    session: str = "default", tab: int | None = None
) -> str:
    """Extract page metadata: title, meta tags, OpenGraph, canonical."""
    runtime, _, ps = await page_for(session, tab)
    data = await ex.extract_meta(ps.page)
    runtime.meter.record("browser_extract_meta")
    return json_safe(data)


async def browser_read_console(
    n: int = 30, drain: bool = False, session: str = "default", tab: int | None = None
) -> str:
    """Read console messages and page errors (JS errors, logs, failed asserts).

    Set drain=true to clear the buffer after reading."""
    runtime, _, ps = await page_for(session, tab)
    logs = ps.drain_console() if drain else ps.console_tail(n)
    errors = list(ps.page_errors)[-10:]
    runtime.meter.record("browser_read_console")
    out = {"console": logs[-n:], "page_errors": errors}
    if not logs and not errors:
        return "No console output captured."
    return json_safe(out)


async def browser_read_dialogs(
    n: int = 10, session: str = "default", tab: int | None = None
) -> str:
    """Read captured alert/confirm/prompt dialogs."""
    runtime, _, ps = await page_for(session, tab)
    dialogs = ps.dialog_tail(n)
    runtime.meter.record("browser_read_dialogs")
    if not dialogs:
        return (
            "No dialogs captured. (Dialogs are auto-accepted and recorded "
            "unless dialog mode is manual.)"
        )
    return json_safe(dialogs)
