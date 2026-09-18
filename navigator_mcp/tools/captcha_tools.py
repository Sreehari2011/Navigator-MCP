"""Captcha tools: detect, auto-solve (Pro + provider key), manual handoff."""

from __future__ import annotations

import asyncio

from fastmcp.exceptions import ToolError

from ..captcha import detector
from ..captcha.providers import SolverError, get_solver
from ._base import json_safe, page_for, ref_locator, require_visible

INJECT_TOKEN_JS = r"""
(token) => {
  // reCAPTCHA v2 / hCaptcha / Turnstile token injection
  const injected = [];
  for (const sel of [
    'textarea.g-recaptcha-response',
    'textarea[name="g-recaptcha-response"]',
    'textarea[name="h-captcha-response"]',
    'textarea[name="cf-turnstile-response"]',
    'input[name="recaptcha_response"]'
  ]) {
    for (const el of document.querySelectorAll(sel)) {
      el.value = token;
      el.style.display = 'block';
      injected.push(el.name || el.className);
    }
  }
  // fire common callbacks
  if (window.onRecaptchaSuccess) { try { window.onRecaptchaSuccess(token); } catch (e) {} }
  if (window.captchaSuccessCallback) { try { window.captchaSuccessCallback(token); } catch (e) {} }
  return injected;
}
"""


async def browser_captcha_detect(
    session: str = "default", tab: int | None = None
) -> str:
    """Detect captcha widgets on the current page (type, evidence, sitekeys)."""
    runtime, _, ps = await page_for(session, tab)
    result = await detector.detect(ps.page)
    runtime.meter.record("browser_captcha_detect")
    return json_safe(result)


async def browser_captcha_solve(
    session: str = "default",
    tab: int | None = None,
    provider: str | None = None,
    ref: str | None = None,
) -> str:
    """Solve the captcha on the current page automatically.

    Needs a provider API key (TWOCAPTCHA_API_KEY or CAPSOLVER_API_KEY).
    Supports reCAPTCHA v2, hCaptcha, Turnstile and plain image captchas
    (via ref pointing at the image element)."""
    runtime, _, ps = await page_for(session, tab)
    detection = await detector.detect(ps.page)
    if not detection["captcha_present"]:
        return "No captcha detected on this page."

    solver = get_solver(provider, runtime.settings)
    if solver is None:
        raise ToolError(
            "No captcha provider configured. Set TWOCAPTCHA_API_KEY or "
            "CAPSOLVER_API_KEY in the environment, or use the manual flow: "
            "browser_captcha_manual_wait()."
        )

    page_url = ps.page.url
    try:
        # --- image captcha via element ref --------------------------------
        if detection["types"] == ["image_captcha"] or (
            "image_captcha" in detection["types"] and not detection["sitekeys"]
        ):
            if not ref:
                raise ToolError(
                    "Image captcha: pass ref pointing at the captcha <img> element."
                )
            locator = await require_visible(ref_locator(ps, ref), ref)
            img_bytes = await locator.screenshot(type="png")
            import base64

            answer = await solver.solve_image(base64.b64encode(img_bytes).decode())
            # type the answer into the captcha input
            injected = await ps.page.evaluate(
                """(answer) => {
                    for (const inp of document.querySelectorAll('input')) {
                        const n = (inp.name || '').toLowerCase() + (inp.id || '').toLowerCase();
                        if (/captcha|verif|human|challenge|security-?code/.test(n)) {
                            inp.value = answer;
                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                            return inp.name || inp.id;
                        }
                    }
                    return null;
                }""",
                answer,
            )
            runtime.meter.record("browser_captcha_solve", captcha=True)
            return (
                f"Image captcha solved (answer typed into {injected or 'input'}). "
                f"Submit the form to verify."
            )

        # --- token captchas --------------------------------------------------
        if not detection["sitekeys"]:
            return json_safe({
                "error": "Captcha present but no sitekey found in DOM.",
                "types": detection["types"],
                "hint": "Try browser_evaluate to locate the sitekey, or use manual flow.",
            })
        sitekey = detection["sitekeys"][0]

        if "recaptcha" in " ".join(detection["types"]):
            token = await solver.solve_recaptcha_v2(sitekey, page_url)
        elif "hcaptcha" in " ".join(detection["types"]):
            token = await solver.solve_hcaptcha(sitekey, page_url)
        elif "turnstile" in " ".join(detection["types"]):
            token = await solver.solve_turnstile(sitekey, page_url)
        else:
            return json_safe({
                "error": f"Unsupported captcha type(s): {detection['types']}",
                "hint": "Use browser_captcha_manual_wait() for this type.",
            })

        injected = await ps.page.evaluate(INJECT_TOKEN_JS, token)
        # Re-check
        await asyncio.sleep(1.5)
        recheck = await detector.detect(ps.page)
        runtime.meter.record("browser_captcha_solve", captcha=True)
        return json_safe({
            "solved": not recheck["captcha_present"],
            "provider": solver.name,
            "token_injected_into": injected,
            "still_present": recheck["types"],
            "next_step": "Submit the form (click the submit button) to complete verification.",
        })
    except SolverError as exc:
        runtime.meter.record("browser_captcha_solve", ok=False)
        raise ToolError(f"Captcha solver error: {exc}") from exc


async def browser_captcha_manual_wait(
    timeout_s: int | None = None,
    poll_s: float = 2.0,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Wait for a human to solve the captcha (requires a visible browser:
    NAVIGATOR_HEADLESS=false or VNC). Polls until the captcha disappears."""
    runtime, _, ps = await page_for(session, tab)
    timeout = timeout_s or runtime.settings.captcha_manual_timeout_s
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        detection = await detector.detect(ps.page)
        if not detection["captcha_present"]:
            return "Captcha is gone — the page accepted the solution. Continue the task."
        await asyncio.sleep(poll_s)
    return (
        f"Captcha still present after {timeout}s. Options: retry, use "
        f"browser_captcha_solve() with a provider key, or inspect the page."
    )
