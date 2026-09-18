"""Network helpers built on the per-page capture wired in ``core.browser``.

Adds:
* **API discovery** — surface background fetch/XHR endpoints (Hypervisor's
  "background APIs" concept) from the capture buffer or a live page.
* **Filter application** — structured capture filters for request recording.
"""

from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from ..core.browser import PageState

API_RESOURCE_TYPES = {"fetch", "xhr", "other"}


def apply_capture_filter(
    ps: PageState,
    resource_types: list[str] | None = None,
    url_contains: str | None = None,
    methods: list[str] | None = None,
) -> None:
    """Configure which requests get recorded for this page."""
    ps.capture_filter = {
        "resource_types": resource_types,
        "url_contains": url_contains,
        "methods": [m.upper() for m in methods] if methods else None,
    }


async def discover_apis(page: Page, ps: PageState, *, limit: int = 40) -> dict[str, Any]:
    """Detect fetch/XHR endpoints, including ones already in the capture buffer.

    Temporarily enables capture to observe live traffic for a few seconds if
    the buffer is empty.
    """
    apis: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entry in ps.requests:
        if entry.resource_type in API_RESOURCE_TYPES and entry.url not in seen:
            seen.add(entry.url)
            apis.append(
                {
                    "method": entry.method,
                    "url": entry.url,
                    "status": entry.status,
                    "source": "capture-buffer",
                }
            )

    if len(apis) < 3:
        # observe live traffic briefly
        was_capturing = ps.network_capture
        ps.network_capture = True
        try:
            import asyncio

            await asyncio.sleep(4)
        finally:
            ps.network_capture = was_capturing
        for entry in ps.requests:
            if entry.resource_type in API_RESOURCE_TYPES and entry.url not in seen:
                seen.add(entry.url)
                apis.append(
                    {
                        "method": entry.method,
                        "url": entry.url,
                        "status": entry.status,
                        "source": "live-observation",
                    }
                )

    apis.sort(key=lambda a: a["url"])
    return {"count": len(apis), "apis": apis[:limit]}
