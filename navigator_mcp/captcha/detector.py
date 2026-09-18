"""Captcha detection across the DOM, iframes and JS globals.

Detects: reCAPTCHA v2/v3 (visible & invisible), hCaptcha, Cloudflare
Turnstile, Arkose/FunCaptcha, GeeTest, Amazon WAF captcha and plain
image captchas (``<img>`` next to a captcha-ish input).
"""

from __future__ import annotations

import re
from typing import Any

from playwright.async_api import Page

DETECT_JS = r"""
() => {
  const found = [];
  const push = (type, evidence) => found.push({type, evidence});

  const html = document.documentElement.outerHTML;

  // --- iframe / script based detectors -----------------------------------
  for (const f of document.querySelectorAll('iframe[src]')) {
    const src = f.src.toLowerCase();
    if (src.includes('google.com/recaptcha')) push('recaptcha_v2', 'iframe: ' + f.src.slice(0, 120));
    if (src.includes('hcaptcha.com')) push('hcaptcha', 'iframe: ' + f.src.slice(0, 120));
    if (src.includes('challenges.cloudflare.com') || src.includes('turnstile')) push('turnstile', 'iframe: ' + f.src.slice(0, 120));
    if (src.includes('funcaptcha.com') || src.includes('arkoselabs')) push('arkose', 'iframe: ' + f.src.slice(0, 120));
    if (src.includes('geetest.com')) push('geetest', 'iframe: ' + f.src.slice(0, 120));
    if (src.includes('aws-waf-captcha')) push('aws_waf', 'iframe: ' + f.src.slice(0, 120));
  }
  for (const s of document.querySelectorAll('script[src]')) {
    const src = s.src.toLowerCase();
    if (src.includes('recaptcha/api.js') || src.includes('recaptcha/enterprise.js')) push('recaptcha', 'script: ' + s.src.slice(0, 120));
    if (src.includes('hcaptcha.com/1/api.js')) push('hcaptcha', 'script: ' + s.src.slice(0, 120));
    if (src.includes('challenges.cloudflare.com/turnstile')) push('turnstile', 'script: ' + s.src.slice(0, 120));
    if (src.includes('geetest.com')) push('geetest', 'script: ' + s.src.slice(0, 120));
  }

  // --- DOM markers ----------------------------------------------------------
  if (document.querySelector('.g-recaptcha, [data-sitekey]')) {
    const el = document.querySelector('.g-recaptcha, [data-sitekey]');
    push('recaptcha_v2', 'marker .g-recaptcha / data-sitekey=' + (el.getAttribute('data-sitekey') || '').slice(0, 60));
  }
  if (document.querySelector('.h-captcha')) push('hcaptcha', 'marker .h-captcha');
  if (document.querySelector('.cf-turnstile')) push('turnstile', 'marker .cf-turnstile');
  if (document.querySelector('#FunCaptcha, .arkose-loader')) push('arkose', 'DOM marker');

  // --- JS globals -----------------------------------------------------------
  if (window.grecaptcha) push('recaptcha_js', 'window.grecaptcha present (v2 or v3)');
  if (window.hcaptcha) push('hcaptcha_js', 'window.hcaptcha present');

  // --- plain image captcha heuristic ---------------------------------------
  const inputs = document.querySelectorAll('input[name]');
  for (const inp of inputs) {
    const n = (inp.name || '').toLowerCase() + (inp.id || '').toLowerCase();
    if (/captcha|verif|human|challenge|security-?code/.test(n)) {
      // look for a nearby image
      let p = inp.parentElement, img = null;
      for (let i = 0; i < 4 && p; i++) {
        img = p.querySelector('img');
        if (img) break;
        p = p.parentElement;
      }
      push('image_captcha', `input[name=${inp.name}]` + (img ? ` + img (${(img.src||'').slice(0,80)})` : ''));
      break;
    }
  }

  // --- sitekeys --------------------------------------------------------------
  const sitekeys = [];
  for (const el of document.querySelectorAll('[data-sitekey]')) {
    sitekeys.push(el.getAttribute('data-sitekey'));
  }
  if (!sitekeys.length && html.includes('sitekey')) {
    const m = html.match(/["']sitekey["']\s*:\s*["']([^"']{10,60})["']/);
    if (m) sitekeys.push(m[1]);
  }

  // dedupe by type+evidence
  const seen = new Set();
  const unique = found.filter(f => {
    const k = f.type + '|' + f.evidence;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });

  return {
    found: unique,
    sitekeys,
    pageUrl: location.href
  };
}
"""


async def detect(page: Page) -> dict[str, Any]:
    """Detect captchas on the page (main frame + same-process children)."""
    results: dict[str, Any] = {
        "found": [],
        "sitekeys": [],
        "page_url": page.url,
        "frames_checked": 1,
    }
    try:
        main = await page.evaluate(DETECT_JS)
        results["found"].extend(main["found"])
        results["sitekeys"].extend(main["sitekeys"])
    except Exception as exc:
        results["error"] = f"main frame scan failed: {exc}"

    for frame in page.frames[1:]:
        try:
            if not frame.url or frame.url == "about:blank":
                continue
            fraw = await frame.evaluate(DETECT_JS)
            for item in fraw["found"]:
                item["evidence"] = f"[frame] {item['evidence']}"
            results["found"].extend(fraw["found"])
            results["sitekeys"].extend(fraw["sitekeys"])
            results["frames_checked"] += 1
        except Exception:
            continue

    # collapse to distinct types
    types = sorted({f["type"] for f in results["found"]})
    results["types"] = types
    results["captcha_present"] = bool(types)
    results["sitekeys"] = list(dict.fromkeys(results["sitekeys"]))[:5]
    return results


# ---------------------------------------------------------------------------
# Provider-agnostic sitekey hints for invisible v3
# ---------------------------------------------------------------------------

SITEKEY_RE = re.compile(r"sitekey[\"']?\s*[:=]\s*[\"']([0-9A-Za-z_-]{20,60})[\"']", re.I)


def extract_sitekey_from_html(html: str) -> str | None:
    m = SITEKEY_RE.search(html or "")
    return m.group(1) if m else None
