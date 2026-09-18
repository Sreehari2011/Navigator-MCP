"""Security testing tools — the Hypervisor suite as first-class MCP tools.

Everything is always unlocked (no tiers, no gating). All tools honor the
engagement scope (security_set_scope).
"""

from __future__ import annotations

import asyncio

from fastmcp.exceptions import ToolError

from ..security import passive
from ..security import waf as waf_mod
from ..security.http_client import raw_request
from ..security.oob import OOBSession
from ._base import json_safe, page_for, ref_locator, require_visible, rt


async def security_scan_page(
    session: str = "default",
    tab: int | None = None,
    include_emails: bool = False,
) -> str:
    """Passively scan the current page for security issues — zero payloads:

    missing security headers, cookie flags, exposed secrets/keys, internal
    IPs, stack traces, mixed content and exposed files."""
    runtime, _, ps = await page_for(session, tab)
    page = ps.page
    try:
        headers = (
            ps.last_document_response["headers"] if ps.last_document_response else {}
        )
        text = await page.inner_text("body")
        urls = await page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'a[href], script[src], img[src], iframe[src]'))"
            ".map(el => el.href || el.src).filter(Boolean).slice(0, 300)"
        )
    except Exception as exc:
        raise ToolError(f"Page scan failed: {exc}") from exc

    alerts = passive.scan_page(
        headers=headers,
        text=text[:60000],
        urls=urls,
        page_is_https=page.url.startswith("https"),
    )
    if include_emails:
        alerts.extend(passive.scan_text(text[:60000], include_emails=True))
    alerts = list(dict.fromkeys(alerts))

    runtime.meter.record("security_scan_page", security=True)
    if not alerts:
        return json_safe({
            "url": page.url,
            "alerts": [],
            "note": "No passive findings. Note: response headers are only "
                    "available after a real navigation in this tab.",
        })
    return json_safe({
        "url": page.url,
        "alert_count": len(alerts),
        "alerts": alerts,
        "severity_hint": "Review SECRET/LEAK findings first — they are the "
                          "highest-impact passive findings.",
    })


async def security_detect_waf(
    url: str | None = None,
    use_wafw00f: bool = True,
    session: str = "default",
) -> str:
    """Detect the WAF/CDN protecting a target. Uses the current page's
    response when url is omitted; header fingerprinting always, wafw00f
    (if installed) as a bonus."""
    runtime = rt()
    if url:
        runtime.scope_guard(url)
        result = await raw_request("GET", url, max_body_chars=4000)
        header_result = waf_mod.detect_from_headers(
            result["headers"], result["status_code"], result.get("body", "")
        )
    else:
        _, _, ps = await page_for(session)
        if not ps.last_document_response:
            raise ToolError(
                "No page response recorded yet — navigate to the target first "
                "or pass an explicit url."
            )
        doc = ps.last_document_response
        header_result = waf_mod.detect_from_headers(doc["headers"], doc["status"])

    w00f = None
    target = url or ps.page.url
    if use_wafw00f:
        w00f = waf_mod.detect_with_wafw00f(target)

    runtime.meter.record("security_detect_waf", security=True)
    return json_safe({"target": target, "headers": header_result, "wafw00f": w00f})


async def security_http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    cookies: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    allow_redirects: bool = True,
    verify_tls: bool = False,
    timeout_s: float = 20.0,
) -> str:
    """Raw HTTP request with full control (Hypervisor's advanced_http_request
    evolved): method/headers/body/cookies/params, redirect tracing, timing and
    automatic passive scanning of the response. Scope-enforced."""
    runtime = rt()
    runtime.scope_guard(url)
    try:
        result = await raw_request(
            method,
            url,
            headers=headers,
            body=body,
            cookies=cookies,
            params=params,
            allow_redirects=allow_redirects,
            verify_tls=verify_tls,
            timeout=timeout_s,
        )
    except Exception as exc:
        raise ToolError(f"HTTP request failed: {exc}") from exc
    runtime.meter.record("security_http_request", security=True)
    return json_safe(result, max_chars=26000)


async def security_oob_generate(tag: str) -> str:
    """Generate a unique Out-of-Band detection domain (blind SSRF/XSS/RCE/XXE).

    Inject the returned domain into the target; any DNS/HTTP/SMTP interaction
    proves the injection. Check results with security_oob_poll()."""
    runtime = rt()
    try:
        oob_session = await runtime.oob.get_session()
    except RuntimeError as exc:
        raise ToolError(str(exc)) from exc
    domain = oob_session.generate_payload(tag)
    runtime.meter.record("security_oob_generate", security=True)
    return (
        f"OOB Payload Generated: {domain}\n"
        f"Inject this into the target (URL param, form field, header...). "
        f"Poll for callbacks later with security_oob_poll(). "
        f"Server: {runtime.settings.oob_server}"
    )


async def security_oob_poll() -> str:
    """Poll the OOB server for blind callbacks (DNS/HTTP/SMTP interactions)."""
    runtime = rt()
    oob_session = await runtime.oob.get_session()
    try:
        interactions = await oob_session.poll()
    except Exception as exc:
        raise ToolError(f"OOB poll failed: {exc}") from exc
    runtime.meter.record("security_oob_poll", security=True)
    return OOBSession.format_interactions(interactions)


async def security_oob_reset() -> str:
    """Start a fresh OOB session (new correlation ID — old payload domains
    stop resolving). Use between engagements."""
    runtime = rt()
    try:
        session = await runtime.oob.reset()
    except RuntimeError as exc:
        raise ToolError(str(exc)) from exc
    runtime.meter.record("security_oob_reset", security=True)
    return f"New OOB session active. Base domain: {session.base_domain}"


async def security_set_scope(
    action: str = "status", domains: list[str] | None = None
) -> str:
    """Manage the engagement scope — the authorized-target allowlist.

    Actions: "set" (restrict navigation + security tools to these domains,
    wildcards like *.example.com allowed), "clear", "status".
    Always set the scope before security testing."""
    runtime = rt()
    if action == "set":
        if not domains:
            raise ToolError("domains list required for action=set")
        runtime.scope.set_engagement(domains)
    elif action == "clear":
        runtime.scope.clear_engagement()
    elif action != "status":
        raise ToolError("action must be set, clear, or status")
    return json_safe(runtime.scope.status())


async def security_test_xss(
    ref: str,
    payload: str,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Inject an XSS test payload into a field and observe the reaction:
    dialogs (alert), console errors and DOM reflection.

    Example payload: <img src=x onerror=alert(1)>"""
    runtime = rt()
    runtime_, _, ps = await page_for(session, tab)
    locator = await require_visible(ref_locator(ps, ref), ref)

    before_dialogs = len(ps.dialogs)
    before_console = len(ps.console)

    try:
        await locator.fill(payload, timeout=runtime.settings.action_timeout_ms)
        # fire common events so frameworks pick up the value
        await locator.evaluate(
            """el => {
                for (const ev of ['input', 'change', 'keyup']) {
                    el.dispatchEvent(new Event(ev, {bubbles: true}));
                }
            }"""
        )
    except Exception as exc:
        raise ToolError(f"Payload injection into {ref} failed: {exc}") from exc

    # observe for 3 seconds
    await asyncio.sleep(3)

    new_dialogs = list(ps.dialogs)[before_dialogs:]
    new_console = list(ps.console)[before_console:]
    try:
        dom_reflected = await ps.page.evaluate(
            "(p) => document.documentElement.outerHTML.includes(p.slice(0, 24))",
            payload,
        )
    except Exception:
        dom_reflected = None

    verdict = "NOT_CONFIRMED"
    if new_dialogs:
        verdict = "XSS CONFIRMED — dialog fired (check dialog content for your marker)"
    elif dom_reflected:
        verdict = (
            "REFLECTED — payload present in DOM; no dialog fired "
            "(may be sanitized or needs interaction)"
        )

    runtime.meter.record("security_test_xss", security=True)
    return json_safe({
        "ref": ref,
        "payload": payload[:200],
        "verdict": verdict,
        "new_dialogs": new_dialogs,
        "new_console": new_console[-8:],
        "reflected_in_dom": dom_reflected,
        "tip": "If not reflected, try submitting the form / triggering the app's "
               "save action, then re-check browser_read_dialogs().",
    })
