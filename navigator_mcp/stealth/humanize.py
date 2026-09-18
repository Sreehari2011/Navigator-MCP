"""Human-like input synthesis: curved mouse movement and jittered typing.

Bot-detection systems (Datadome, PerimeterX, Akamai) score pointer telemetry.
These helpers replace Playwright's instantaneous, perfectly-straight input with
plausible human motion: multi-segment Bézier paths with overshoot + correction,
variable-velocity typing with occasional pauses and typo-fixes.
"""

from __future__ import annotations

import asyncio
import math
import random

from playwright.async_api import Locator, Page


async def _bezier_points(
    x0: float, y0: float, x1: float, y1: float, *, steps: int | None = None
) -> list[tuple[float, float]]:
    """Sample a quadratic Bézier with a randomized control point."""
    dist = math.hypot(x1 - x0, y1 - y0)
    if steps is None:
        steps = max(8, min(40, int(dist / 18)))
    # control point offset perpendicular to the path
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    offset = random.uniform(-0.18, 0.18) * max(dist, 40)
    angle = math.atan2(y1 - y0, x1 - x0) + math.pi / 2
    cx, cy = mx + offset * math.cos(angle), my + offset * math.sin(angle)

    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        # ease-in-out so speed ramps like a real hand
        te = t * t * (3 - 2 * t)
        bx = (1 - te) ** 2 * x0 + 2 * (1 - te) * te * cx + te**2 * x1
        by = (1 - te) ** 2 * y0 + 2 * (1 - te) * te * cy + te**2 * y1
        pts.append((bx, by))
    return pts


async def human_mouse_to(
    page: Page, x: float, y: float, *, overshoot: bool = True
) -> None:
    """Move the mouse along a human-looking path to (x, y) in viewport coords."""
    try:
        pos = await page.evaluate(
            "() => ({x: window.__navigatorMouseX || 0, y: window.__navigatorMouseY || 0})"
        )
        sx, sy = float(pos.get("x", 0)), float(pos.get("y", 0))
    except Exception:
        sx, sy = random.uniform(100, 400), random.uniform(100, 300)

    target_x, target_y = x, y
    if overshoot and random.random() < 0.55:
        target_x = x + random.uniform(-14, 14)
        target_y = y + random.uniform(-14, 14)

    for (bx, by) in await _bezier_points(sx, sy, target_x, target_y):
        await page.mouse.move(bx, by)
        await asyncio.sleep(random.uniform(0.004, 0.014))

    # correction step to the real target
    if (target_x, target_y) != (x, y):
        for (bx, by) in await _bezier_points(target_x, target_y, x, y, steps=6):
            await page.mouse.move(bx, by)
            await asyncio.sleep(random.uniform(0.006, 0.016))

    try:
        await page.evaluate(
            "([px, py]) => { window.__navigatorMouseX = px; window.__navigatorMouseY = py; }",
            [x, y],
        )
    except Exception:
        pass


async def human_click(page: Page, locator: Locator) -> None:
    """Move along a curve to the element center, then click with tiny jitter."""
    box = await locator.bounding_box()
    if not box:
        await locator.click()
        return
    x = box["x"] + box["width"] / 2 + random.uniform(-2, 2)
    y = box["y"] + box["height"] / 2 + random.uniform(-2, 2)
    await human_mouse_to(page, x, y)
    await asyncio.sleep(random.uniform(0.05, 0.16))
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.035, 0.11))
    await page.mouse.up()


async def human_type(page: Page, locator: Locator, text: str, *, wpm: int = 220) -> None:
    """Focus the field, then type with per-key delays, pauses and typo fixes."""
    await locator.click()
    await asyncio.sleep(random.uniform(0.08, 0.2))

    base_delay = 60_000 / (max(wpm, 80) * 5) / 1000  # ~ms per char

    i = 0
    while i < len(text):
        ch = text[i]
        if random.random() < 0.015 and ch.isalnum() and i + 1 < len(text):
            # rare typo + correction
            wrong = random.choice("abcdefghijklmnopqrstuvwxyz")
            await page.keyboard.type(wrong, delay=int(base_delay * random.uniform(0.7, 1.2)))
            await asyncio.sleep(random.uniform(0.12, 0.3))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.keyboard.type(ch, delay=int(base_delay * random.uniform(0.55, 1.6)))
        # thinking pauses after space/punctuation
        if ch in ".@_-/ " and random.random() < 0.25:
            await asyncio.sleep(random.uniform(0.15, 0.55))
        i += 1


async def human_scroll(
    page: Page, direction: str, *, amount_px: int | None = None
) -> None:
    """Scroll in a few uneven bursts instead of one jump."""
    delta_map = {"down": 1, "up": -1}
    sign = delta_map.get(direction, 1)
    if direction in {"top", "bottom"}:
        await page.evaluate(
            "dir => window.scrollTo({top: dir === 'bottom' "
            "? document.body.scrollHeight : 0, behavior: 'smooth'})",
            direction,
        )
        await asyncio.sleep(random.uniform(0.4, 0.8))
        return
    remaining = amount_px if amount_px is not None else int(
        (await page.evaluate("() => window.innerHeight")) * 0.85
    )
    while remaining > 0:
        chunk = int(remaining * random.uniform(0.35, 0.7))
        chunk = max(chunk, 40)
        await page.mouse.wheel(0, sign * chunk)
        remaining -= chunk
        await asyncio.sleep(random.uniform(0.12, 0.4))
