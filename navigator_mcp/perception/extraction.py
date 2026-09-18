"""Smart content extraction: text, links, forms, metadata, tables.

All extractors return LLM-ready structures and support offset/limit pagination
so huge pages never blow the context window.
"""

from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Frame, Page

TEXT_SELECTORS = ["main", "article", "#content", "#main", '[role="main"]', "body"]


def _clean_text(text: str) -> str:
    text = re.sub(r"\n\s*\n+", "\n\n", text or "")
    return text.strip()


async def _target(page: Page, ref: str | None, frame_index: int | None):
    """Resolve a ref to a locator, or return None for whole-page operations."""
    if not ref:
        return None
    from .snapshot import parse_ref

    fidx, selector = parse_ref(ref)
    if frame_index is not None:
        fidx = frame_index
    if fidx is None:
        return page.locator(selector).first
    frames = page.frames
    if not 0 < fidx < len(frames):
        raise IndexError(f"frame index {fidx} out of range (1..{len(frames) - 1})")
    frame: Frame = frames[fidx]
    return frame.locator(selector).first


async def extract_text(
    page: Page, ref: str | None = None, *, offset: int = 0, limit: int = 12000
) -> dict[str, Any]:
    """Whole-page (smart main-content) or per-element text extraction."""
    locator = await _target(page, ref, None)
    if locator is not None:
        text = _clean_text(await locator.inner_text())
    else:
        text = ""
        for sel in TEXT_SELECTORS:
            try:
                if await page.locator(sel).count() > 0:
                    candidate = await page.locator(sel).first.inner_text()
                    if candidate and len(candidate) > 200:
                        text = candidate
                        break
                    if candidate and not text:
                        text = candidate
            except Exception:
                continue
        text = _clean_text(text or (await page.inner_text("body")))

    total = len(text)
    chunk = text[offset : offset + limit]
    return {
        "url": page.url,
        "total_chars": total,
        "offset": offset,
        "returned_chars": len(chunk),
        "has_more": offset + limit < total,
        "text": chunk,
    }


async def extract_html(
    page: Page, ref: str | None = None, *, offset: int = 0, limit: int = 20000
) -> dict[str, Any]:
    """Outer HTML of an element (by ref) or the whole document."""
    locator = await _target(page, ref, None)
    if locator is not None:
        html = await locator.evaluate("el => el.outerHTML")
    else:
        html = await page.content()
    total = len(html)
    return {
        "url": page.url,
        "total_chars": total,
        "offset": offset,
        "returned_chars": len(html[offset : offset + limit]),
        "has_more": offset + limit < total,
        "html": html[offset : offset + limit],
    }


async def extract_links(page: Page, *, limit: int = 100) -> dict[str, Any]:
    """All anchors with resolved hrefs (deduplicated)."""
    links = await page.evaluate(
        """() => {
        const seen = new Set();
        const out = [];
        for (const a of document.querySelectorAll('a[href]')) {
            const href = a.href;
            if (!href || seen.has(href)) continue;
            seen.add(href);
            out.push({
                text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 80),
                href
            });
            if (out.length >= 300) break;
        }
        return out;
    }"""
    )
    return {"count": len(links), "links": links[:limit]}


async def extract_meta(page: Page) -> dict[str, Any]:
    """Title, meta tags, OpenGraph/Twitter cards, canonical + base."""
    return await page.evaluate(
        """() => {
        const meta = {};
        for (const m of document.querySelectorAll('meta')) {
            const key = m.getAttribute('name') || m.getAttribute('property');
            if (key && m.getAttribute('content')) meta[key] = m.getAttribute('content');
        }
        const canonical = document.querySelector('link[rel="canonical"]');
        const base = document.querySelector('base');
        return {
            url: location.href,
            title: document.title,
            meta,
            canonical: canonical ? canonical.href : null,
            base: base ? base.href : null,
            doctype: document.doctype ? document.doctype.name : null
        };
    }"""
    )


async def extract_forms(page: Page) -> dict[str, Any]:
    """Forms with their fields — the map for form-filling and automation."""
    return await page.evaluate(
        """() => {
        return Array.from(document.querySelectorAll('form')).slice(0, 20).map((f, i) => ({
            index: i,
            id: f.id || null,
            name: f.getAttribute('name') || null,
            action: f.action || null,
            method: (f.method || 'get').toUpperCase(),
            fields: Array.from(f.querySelectorAll('input, select, textarea')).slice(0, 40).map(el => ({
                tag: el.tagName.toLowerCase(),
                type: el.type || null,
                name: el.name || null,
                id: el.id || null,
                value: (el.type === 'password') ? '(password)' : String(el.value || '').slice(0, 60),
                required: el.required || false,
                hidden: el.type === 'hidden' || getComputedStyle(el).display === 'none'
            }))
        }));
    }"""
    )


async def extract_tables(page: Page, *, limit_rows: int = 50) -> dict[str, Any]:
    """Tables converted to row arrays (much cheaper for the LLM than HTML)."""
    return await page.evaluate(
        """(limitRows) => {
        return Array.from(document.querySelectorAll('table')).slice(0, 10).map((t, i) => {
            const rows = [];
            for (const tr of t.querySelectorAll('tr')) {
                rows.push(Array.from(tr.querySelectorAll('th,td')).map(
                    c => (c.innerText || '').trim().slice(0, 120)
                ));
                if (rows.length >= limitRows) break;
            }
            return { index: i, rows };
        });
    }""",
        limit_rows,
    )
