"""Vision tools — screenshots (native image content) and PDF export."""

from __future__ import annotations

from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image

from ._base import page_for, ref_locator, require_visible


async def browser_screenshot(
    session: str = "default",
    tab: int | None = None,
    area: str = "viewport",
    ref: str | None = None,
    format: str = "png",
    quality: int = 70,
) -> Image:
    """Take a screenshot and return it as an image (for vision-capable LLMs).

    area: "viewport" (visible part), "full" (entire page), or "element"
    (requires ref). format: png or jpeg (jpeg is much smaller — prefer it
    for large pages).
    """
    runtime, _, ps = await page_for(session, tab)
    if area not in {"viewport", "full", "element"}:
        raise ToolError("area must be viewport, full, or element")
    if area == "element" and not ref:
        raise ToolError("area=element requires a ref")
    kwargs: dict = {"type": format, "quality": quality} if format == "jpeg" else {"type": "png"}
    try:
        if area == "element":
            locator = await require_visible(ref_locator(ps, ref or ""), ref or "")
            data = await locator.screenshot(**kwargs)
        elif area == "full":
            data = await ps.page.screenshot(full_page=True, **kwargs)
        else:
            data = await ps.page.screenshot(**kwargs)
    except Exception as exc:
        raise ToolError(f"Screenshot failed: {exc}") from exc
    runtime.meter.record("browser_screenshot")
    return Image(data=data, format=format)


async def browser_save_pdf(
    path: str,
    session: str = "default",
    tab: int | None = None,
    format: str = "A4",
    print_background: bool = True,
) -> str:
    """Save the current page as a PDF (Chromium only)."""
    runtime, _, ps = await page_for(session, tab)
    try:
        await ps.page.emulate_media(media="print")
        await ps.page.pdf(path=path, format=format, print_background=print_background)
    except Exception as exc:
        raise ToolError(f"PDF export failed: {exc}") from exc
    runtime.meter.record("browser_save_pdf")
    return f"PDF saved to {path}"
