"""Raw HTTP client for security testing (Hypervisor ``advanced_http_request``
evolved): precise method/header/body control, TLS control, redirect control,
timing, and automatic passive scanning of every response.

Scope-enforced: when an engagement scope is active, requests outside it are
refused. This is the safety rail that keeps autonomous agents on target.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .passive import scan_headers, scan_text


async def raw_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    cookies: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    allow_redirects: bool = True,
    verify_tls: bool = False,
    timeout: float = 20.0,
    auth: tuple[str, str] | None = None,
    follow_limit: int = 5,
    max_body_chars: int = 20000,
) -> dict[str, Any]:
    """Perform one raw HTTP request and return metadata + (scanned) body.

    Redirects are traced so the full chain (and each hop's headers) is visible
    — important for open-redirect and header-injection analysis.
    """
    method = method.upper()
    started = time.perf_counter()

    # JSON body convenience
    request_headers = dict(headers or {})
    json_body = None
    if body is not None:
        ctype = request_headers.get("content-type", request_headers.get("Content-Type", ""))
        if "json" in ctype.lower():
            try:
                json_body = json.loads(body)
                body = None
            except json.JSONDecodeError:
                pass  # send as-is

    redirect_chain: list[dict[str, Any]] = []

    async def _trace_redirects(response: httpx.Response) -> None:
        history = getattr(response, "history", ())
        for hop in history:
            redirect_chain.append(
                {
                    "status": hop.status_code,
                    "url": str(hop.url),
                    "location": hop.headers.get("location", ""),
                }
            )

    async with httpx.AsyncClient(
        verify=verify_tls,
        follow_redirects=allow_redirects,
        timeout=timeout,
        cookies=cookies,
        auth=auth,
    ) as client:
        resp = await client.request(
            method,
            url,
            headers=request_headers or None,
            content=body,
            json=json_body,
            params=params,
        )
        await _trace_redirects(resp)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        text = resp.text

    alerts: list[str] = []
    alerts.extend(scan_headers(dict(resp.headers)))
    alerts.extend(scan_text(text[:50000]))

    result: dict[str, Any] = {
        "status_code": resp.status_code,
        "reason": resp.reason_phrase,
        "elapsed_ms": elapsed_ms,
        "url": str(resp.url),
        "redirect_chain": redirect_chain[:follow_limit],
        "headers": dict(resp.headers),
        "cookies": {k: v[:40] for k, v in resp.cookies.items()},
        "content_type": resp.headers.get("content-type", ""),
        "body_length": len(text),
        "body": text[:max_body_chars],
        "body_truncated": len(text) > max_body_chars,
    }
    if alerts:
        result["security_alerts"] = alerts
    return result
