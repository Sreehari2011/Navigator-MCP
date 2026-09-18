"""Interaction tools — ref-driven, optionally humanized."""

from __future__ import annotations

import asyncio

from fastmcp.exceptions import ToolError

from ..stealth.humanize import human_click, human_scroll, human_type
from ._base import maybe_snapshot, page_for, ref_locator, require_visible


async def _settle_and_snapshot(runtime, ps, *, force=False) -> str:
    await runtime.browser.settle(ps, wait_network_idle=False)
    if runtime.settings.auto_snapshot_on_change:
        return await maybe_snapshot(ps, force=force)
    return ""


async def browser_click(
    ref: str,
    session: str = "default",
    tab: int | None = None,
    double: bool = False,
    button: str = "left",
) -> str:
    """Click an element by its ref from the snapshot (e.g. e12).

    Uses human-like mouse movement when the session has humanization enabled.
    """
    runtime, sess, ps = await page_for(session, tab)
    locator = await require_visible(ref_locator(ps, ref), ref)
    try:
        if sess.humanize and button == "left" and not double:
            await human_click(ps.page, locator)
        else:
            await locator.click(
                button=button,
                double_click=double,
                timeout=runtime.settings.action_timeout_ms,
            )
    except Exception as exc:
        raise ToolError(f"Click on {ref} failed: {exc}") from exc
    runtime.meter.record("browser_click")
    snap = await _settle_and_snapshot(runtime, ps)
    result = f"Clicked {ref}."
    if snap:
        result += "\n\n" + snap
    return result


async def browser_click_text(
    text: str,
    session: str = "default",
    tab: int | None = None,
    nth: int = 0,
) -> str:
    """Fallback click by visible text (use when no ref is available)."""
    runtime, _, ps = await page_for(session, tab)
    locator = ps.page.get_by_text(text, exact=False).nth(nth)
    if await locator.count() == 0:
        locator = ps.page.get_by_role("button", name=text).nth(nth)
    if await locator.count() == 0:
        raise ToolError(f"No element with text {text!r} found")
    try:
        await locator.first.click(timeout=runtime.settings.action_timeout_ms)
    except Exception as exc:
        raise ToolError(f"Click on text {text!r} failed: {exc}") from exc
    runtime.meter.record("browser_click_text")
    snap = await _settle_and_snapshot(runtime, ps)
    result = f"Clicked element with text {text!r}."
    if snap:
        result += "\n\n" + snap
    return result


async def browser_fill(
    ref: str,
    text: str,
    session: str = "default",
    tab: int | None = None,
    submit: bool = False,
) -> str:
    """Fill a field by ref. Set submit=true to press Enter afterwards."""
    runtime, sess, ps = await page_for(session, tab)
    locator = await require_visible(ref_locator(ps, ref), ref)
    try:
        if sess.humanize and len(text) <= 120:
            await human_type(ps.page, locator, text)
        else:
            await locator.fill(text, timeout=runtime.settings.action_timeout_ms)
        if submit:
            await ps.page.keyboard.press("Enter")
    except Exception as exc:
        raise ToolError(f"Fill on {ref} failed: {exc}") from exc
    runtime.meter.record("browser_fill")
    snap = await _settle_and_snapshot(runtime, ps)
    result = f"Filled {ref} with {len(text)} chars" + (" and pressed Enter" if submit else "")
    if snap:
        result += "\n\n" + snap
    return result


async def browser_fill_form(
    fields: list[dict[str, str]],
    session: str = "default",
    tab: int | None = None,
    submit: bool = False,
) -> str:
    """Fill multiple fields in one call — much faster than one fill per field.

    Each item: {"ref": "e5", "value": "text"}. Optionally submits the form
    (presses Enter on the last field).
    """
    runtime, _, ps = await page_for(session, tab)
    if not fields:
        raise ToolError("fields must be a non-empty list of {ref, value}")
    filled = 0
    for item in fields:
        ref = item.get("ref") or ""
        value = item.get("value", "")
        locator = await require_visible(ref_locator(ps, ref), ref)
        try:
            await locator.fill(value, timeout=runtime.settings.action_timeout_ms)
            filled += 1
        except Exception as exc:
            raise ToolError(f"Fill on {ref} failed: {exc}") from exc
    if submit and fields:
        last_ref = fields[-1]["ref"]
        await ref_locator(ps, last_ref).first.press("Enter")
    runtime.meter.record("browser_fill_form")
    snap = await _settle_and_snapshot(runtime, ps)
    result = f"Filled {filled} fields" + (" and submitted" if submit else "") + "."
    if snap:
        result += "\n\n" + snap
    return result


async def browser_select_option(
    ref: str,
    value: str,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Select an option in a dropdown (combobox) by ref. Value = option label."""
    runtime, _, ps = await page_for(session, tab)
    locator = await require_visible(ref_locator(ps, ref), ref)
    try:
        await locator.select_option(value, timeout=runtime.settings.action_timeout_ms)
    except Exception as exc:
        raise ToolError(
            f"Select on {ref} failed (value={value!r}). "
            f"Tip: pass the option's visible label."
        ) from exc
    runtime.meter.record("browser_select_option")
    return f"Selected {value!r} in {ref}."


async def browser_hover(
    ref: str, session: str = "default", tab: int | None = None
) -> str:
    """Hover over an element by ref (reveals menus/tooltips)."""
    runtime, _, ps = await page_for(session, tab)
    locator = await require_visible(ref_locator(ps, ref), ref)
    try:
        await locator.hover(timeout=runtime.settings.action_timeout_ms)
    except Exception as exc:
        raise ToolError(f"Hover on {ref} failed: {exc}") from exc
    runtime.meter.record("browser_hover")
    await asyncio.sleep(0.3)
    snap = await _settle_and_snapshot(runtime, ps)
    result = f"Hovered {ref}."
    if snap:
        result += "\n\n" + snap
    return result


async def browser_press_key(
    key: str,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Press a key (e.g. Enter, Escape, Tab, ArrowDown, Control+a)."""
    runtime, _, ps = await page_for(session, tab)
    try:
        await ps.page.keyboard.press(key)
    except Exception as exc:
        raise ToolError(f"Key press {key!r} failed: {exc}") from exc
    runtime.meter.record("browser_press_key")
    snap = await _settle_and_snapshot(runtime, ps)
    result = f"Pressed {key}."
    if snap:
        result += "\n\n" + snap
    return result


async def browser_drag(
    ref_a: str,
    ref_b: str,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Drag element ref_a onto element ref_b."""
    runtime, _, ps = await page_for(session, tab)
    la = await require_visible(ref_locator(ps, ref_a), ref_a)
    lb = await require_visible(ref_locator(ps, ref_b), ref_b)
    try:
        await la.drag_to(lb, timeout=runtime.settings.action_timeout_ms)
    except Exception as exc:
        raise ToolError(f"Drag {ref_a} -> {ref_b} failed: {exc}") from exc
    runtime.meter.record("browser_drag")
    snap = await _settle_and_snapshot(runtime, ps)
    return f"Dragged {ref_a} onto {ref_b}." + (("\n\n" + snap) if snap else "")


async def browser_upload_file(
    ref: str,
    path: str,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Upload a local file. Ref may point to the file input or its trigger button."""
    import os

    runtime, _, ps = await page_for(session, tab)
    if not os.path.isfile(path):
        raise ToolError(f"Local file not found: {path}")
    locator = await require_visible(ref_locator(ps, ref), ref)
    try:
        tag = await locator.evaluate("el => el.tagName.toLowerCase()")
        if tag == "input":
            await locator.set_input_files(path)
        else:
            async with ps.page.expect_file_chooser() as fc_info:
                await locator.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(path)
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"Upload to {ref} failed: {exc}") from exc
    runtime.meter.record("browser_upload_file")
    snap = await _settle_and_snapshot(runtime, ps)
    return f"Uploaded {path} via {ref}." + (("\n\n" + snap) if snap else "")


async def browser_scroll(
    direction: str = "down",
    amount_px: int | None = None,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Scroll the page. Directions: down, up, top, bottom. Optional pixel amount."""
    runtime, sess, ps = await page_for(session, tab)
    if direction not in {"down", "up", "top", "bottom"}:
        raise ToolError("direction must be one of: down, up, top, bottom")
    try:
        if sess.humanize and direction in {"down", "up"}:
            await human_scroll(ps.page, direction, amount_px=amount_px)
        else:
            script = {
                "down": f"window.scrollBy(0, {amount_px or 800})",
                "up": f"window.scrollBy(0, -{amount_px or 800})",
                "top": "window.scrollTo(0, 0)",
                "bottom": "window.scrollTo(0, document.body.scrollHeight)",
            }[direction]
            await ps.page.evaluate(script)
    except Exception as exc:
        raise ToolError(f"Scroll failed: {exc}") from exc
    runtime.meter.record("browser_scroll")
    await asyncio.sleep(0.2)
    snap = await maybe_snapshot(ps, force=True)  # scroll changes visible content
    result = f"Scrolled {direction}" + (f" {amount_px}px" if amount_px else "") + "."
    if snap:
        result += "\n\n" + snap
    return result
