"""Pluggable captcha solver providers — bring your own API key.

Supported:
  * **2Captcha** (``TWOCAPTCHA_API_KEY``)  — image-to-text, reCAPTCHA v2,
    hCaptcha, Turnstile.
  * **CapSolver** (``CAPSOLVER_API_KEY``)  — reCAPTCHA v2, hCaptcha, Turnstile.

Both are async, poll-based clients. No keys are ever persisted; they are read
from the environment at solve time. Without a provider key you still get
detection + the manual handoff flow (browser_captcha_manual_wait).
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, Protocol

import httpx


class CaptchaSolver(Protocol):
    name: str

    async def balance(self) -> float: ...

    async def solve_image(self, image_b64: str) -> str: ...
    async def solve_recaptcha_v2(self, sitekey: str, page_url: str) -> str: ...
    async def solve_hcaptcha(self, sitekey: str, page_url: str) -> str: ...
    async def solve_turnstile(self, sitekey: str, page_url: str) -> str: ...


class SolverError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# 2Captcha
# ---------------------------------------------------------------------------

class TwoCaptchaSolver:
    """2Captcha.com API client (in.php / res.php polling)."""

    BASE = "https://2captcha.com"

    def __init__(self, api_key: str) -> None:
        self.name = "2captcha"
        self.api_key = api_key

    async def _submit(self, params: dict[str, Any]) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.BASE}/in.php", data=params)
            body = resp.text
            if not body.startswith("OK|"):
                raise SolverError(f"2captcha submit failed: {body}")
            return body.split("|", 1)[1]

    async def _poll(self, request_id: str, timeout: float = 180.0) -> str:
        deadline = time.monotonic() + timeout
        async with httpx.AsyncClient(timeout=30) as client:
            while time.monotonic() < deadline:
                await asyncio.sleep(5.0)
                resp = await client.get(
                    f"{self.BASE}/res.php",
                    params={"key": self.api_key, "action": "get", "id": request_id},
                )
                body = resp.text
                if body.startswith("OK|"):
                    return body.split("|", 1)[1]
                if body != "CAPCHA_NOT_READY":
                    raise SolverError(f"2captcha poll failed: {body}")
        raise SolverError("2captcha timed out")

    async def balance(self) -> float:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.BASE}/res.php",
                params={"key": self.api_key, "action": "getbalance"},
            )
            return float(resp.text)

    async def solve_image(self, image_b64: str) -> str:
        rid = await self._submit(
            {"key": self.api_key, "method": "base64", "body": image_b64, "json": 0}
        )
        return await self._poll(rid)

    async def solve_recaptcha_v2(self, sitekey: str, page_url: str) -> str:
        rid = await self._submit(
            {
                "key": self.api_key,
                "method": "userrecaptcha",
                "googlekey": sitekey,
                "pageurl": page_url,
            }
        )
        return await self._poll(rid)

    async def solve_hcaptcha(self, sitekey: str, page_url: str) -> str:
        rid = await self._submit(
            {
                "key": self.api_key,
                "method": "hcaptcha",
                "sitekey": sitekey,
                "pageurl": page_url,
            }
        )
        return await self._poll(rid)

    async def solve_turnstile(self, sitekey: str, page_url: str) -> str:
        rid = await self._submit(
            {
                "key": self.api_key,
                "method": "turnstile",
                "sitekey": sitekey,
                "pageurl": page_url,
            }
        )
        return await self._poll(rid)


# ---------------------------------------------------------------------------
# CapSolver
# ---------------------------------------------------------------------------

class CapSolverSolver:
    """api.capsolver.com client (createTask / getTaskResult polling)."""

    BASE = "https://api.capsolver.com"

    def __init__(self, api_key: str) -> None:
        self.name = "capsolver"
        self.api_key = api_key

    async def _run_task(self, task: dict[str, Any], timeout: float = 180.0) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.BASE}/createTask",
                json={"clientKey": self.api_key, "task": task},
            )
            data = resp.json()
            if data.get("errorId"):
                raise SolverError(f"capsolver createTask: {data.get('errorDescription')}")
            task_id = data["taskId"]

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                await asyncio.sleep(3.0)
                resp = await client.post(
                    f"{self.BASE}/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                )
                result = resp.json()
                if result.get("status") == "ready":
                    solution = result.get("solution", {})
                    return (
                        solution.get("gRecaptchaResponse")
                        or solution.get("token")
                        or solution.get("text")
                        or ""
                    )
                if result.get("errorId"):
                    raise SolverError(f"capsolver poll: {result.get('errorDescription')}")
        raise SolverError("capsolver timed out")

    async def balance(self) -> float:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.BASE}/getBalance", json={"clientKey": self.api_key}
            )
            return float(resp.json().get("balance", 0.0))

    async def solve_image(self, image_b64: str) -> str:
        return await self._run_task(
            {"type": "ImageToTextTask", "body": image_b64}
        )

    async def solve_recaptcha_v2(self, sitekey: str, page_url: str) -> str:
        return await self._run_task(
            {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": sitekey,
            }
        )

    async def solve_hcaptcha(self, sitekey: str, page_url: str) -> str:
        return await self._run_task(
            {
                "type": "HCaptchaTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": sitekey,
            }
        )

    async def solve_turnstile(self, sitekey: str, page_url: str) -> str:
        return await self._run_task(
            {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": sitekey,
            }
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def get_solver(provider: str | None, settings: Any) -> CaptchaSolver | None:
    """Return the configured solver (priority: explicit > capsolver > 2captcha)."""
    candidates: list[tuple[str, str, type]] = [
        ("capsolver", settings.capsolver_api_key, CapSolverSolver),
        ("2captcha", settings.twocaptcha_api_key, TwoCaptchaSolver),
    ]
    if provider:
        candidates.sort(key=lambda c: 0 if c[0] == provider.lower() else 1)
    for _name, key, cls in candidates:
        if key:
            return cls(key)
    return None


def image_bytes_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
