"""Shared helpers for tool implementations."""

from __future__ import annotations

import json
from typing import Any

from fastmcp.exceptions import ToolError
from playwright.async_api import Locator, Page

from ..core.browser import PageState, Session
from ..perception.snapshot import parse_ref
from ..runtime import NavigatorRuntime, get_runtime


def rt() -> NavigatorRuntime:
    return get_runtime()


async def page_for(
    session: str = "default", tab: int | None = None
) -> tuple[NavigatorRuntime, Session, PageState]:
    """Resolve runtime + session + page state, with friendly errors.

    Lazily creates the "default" session so a fresh server can be driven
    immediately (browser_navigate as the very first call just works).
    """
    runtime = rt()
    if session not in runtime.browser.sessions:
        if session == "default":
            if runtime.browser.sessions:
                runtime.check_session_budget()
            await runtime.browser.ensure_session("default")
        else:
            raise ToolError(
                f"session '{session}' not found. Active sessions: "
                f"{sorted(runtime.browser.sessions) or 'none'}. "
                f"Create one with browser_session_new()."
            )
    try:
        ps = runtime.browser.get_page(session, tab)
        sess = runtime.browser.get_session(session)
    except KeyError as exc:
        raise ToolError(str(exc)) from exc
    except IndexError as exc:
        raise ToolError(str(exc)) from exc
    except RuntimeError as exc:
        raise ToolError(str(exc)) from exc
    return runtime, sess, ps


def ref_locator(ps: PageState, ref: str) -> Locator:
    """Resolve an e-ref (or frame-prefixed fN!eM ref) to a Locator."""
    if not ref or not str(ref).strip():
        raise ToolError("A non-empty element ref is required (e.g. e12 — see browser_snapshot)")
    frame_index, selector = parse_ref(str(ref))
    page: Page = ps.page
    if frame_index is None:
        locator = page.locator(selector).first
    else:
        frames = page.frames
        if not 0 < frame_index < len(frames):
            raise ToolError(
                f"Frame index {frame_index} not available (1..{len(frames) - 1})"
            )
        locator = frames[frame_index].locator(selector).first
    return locator


async def require_visible(locator: Locator, ref: str) -> Locator:
    """Verify the element exists; otherwise raise a helpful error."""
    try:
        count = await locator.count()
    except Exception as exc:
        raise ToolError(f"Could not resolve ref {ref}: {exc}") from exc
    if count == 0:
        raise ToolError(
            f"Element ref '{ref}' not found — the page likely changed. "
            f"Take a fresh snapshot with browser_snapshot() and use the new refs."
        )
    return locator


def json_safe(data: Any, max_chars: int = 6000) -> str:
    """Serialize tool output as compact, bounded JSON text."""
    text = json.dumps(data, ensure_ascii=False, indent=1, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n…[truncated, total {len(text)} chars — refine filters]"
    return text


async def maybe_snapshot(ps: PageState, *, force: bool = False) -> str:
    """Post-action snapshot helper: returns rendered snapshot or '' if unchanged.

    Updates the page's snapshot cache; used by mutating tools so the LLM gets
    the new page state without an extra round-trip.
    """
    runtime = rt()
    from ..perception import snapshot as snap

    try:
        raw = await snap.capture(ps.page, runtime.settings.max_snapshot_nodes)
    except Exception as exc:
        return f"(snapshot unavailable: {exc})"
    h = snap.snapshot_hash(raw)
    if h == ps.last_snapshot_hash and not force:
        return ""
    ps.last_snapshot_hash = h
    ps.last_snapshot_text = snap.render_snapshot(raw)
    ps.snapshot_count += 1
    return ps.last_snapshot_text
