"""FastMCP server assembly: instructions, middleware, transports.

Run modes
---------
* **stdio** (default) — Claude Desktop / Cursor / VS Code / any MCP client.
* **Streamable HTTP** — remote access (e.g. a home server reachable from
  your laptop), optionally behind API keys
  (``navigator-mcp --transport http --host 0.0.0.0 --port 8765``).
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

from . import __version__
from .config import get_settings
from .runtime import get_runtime
from .tools import register_tools

logger = logging.getLogger("navigator.server")

SERVER_INSTRUCTIONS = """\
Navigator is your high-performance browser. Workflow for any web task:

1. PERCEIVE: call browser_snapshot() — you get a compact tree of interactive
   elements, each with a stable [ref=eN] id. The snapshot is CACHED: if a
   page didn't change you get a short "unchanged" notice — that's normal,
   don't re-request. browser_find(pattern) searches elements cheaply.
2. ACT: pass refs to the action tools (browser_click(ref="e5"),
   browser_fill, browser_fill_form for multiple fields at once...).
   After actions that change the page, the new snapshot is included
   automatically — no extra call needed.
3. EXTRACT: browser_extract_text/_html/_links/_forms/_tables/_meta give
   structured data with offset/limit pagination for long pages.

Isolation: sessions are separate browser profiles (cookies/fingerprint/proxy).
Use browser_session_new for logins or parallel tasks; browser_session_save_auth
persists login state across restarts.

Vision: browser_screenshot returns an image — use it when the AX snapshot is
ambiguous (canvas, maps, unusual layouts) or to verify visual results.

CAPTCHAS: browser_captcha_detect finds them; browser_captcha_solve handles
reCAPTCHA/hCaptcha/Turnstile automatically (needs a provider key); the manual
flow (browser_captcha_manual_wait) works with a visible browser.

TRAFFIC: browser_network_* capture and inspect requests; browser_discover_apis
reveals the JSON endpoints behind a page; browser_network_block strips
css/images for fast scrapes.

TIPS:
- If a ref stops resolving, the page changed — take a fresh snapshot.
- browser_read_console reveals JS errors after your actions.
- Block css/images with browser_network_block to speed up scrapes.
- browser_evaluate runs arbitrary JS when you need custom logic.
"""


# ---------------------------------------------------------------------------
# MCP middleware: metering + failure accounting
# ---------------------------------------------------------------------------

class MeteringMiddleware(Middleware):
    """Records failed tool calls (successes are recorded by the tools with
    richer semantics); keeps a wall-clock for slow-tool diagnostics."""
    async def on_call_tool(
        self, context: MiddlewareContext, call_next: CallNext
    ):
        started = time.perf_counter()
        try:
            return await call_next(context)
        except Exception:
            try:
                name = getattr(getattr(context, "message", None), "name", "unknown")
                get_runtime().meter.record(name, ok=False)
            except Exception:
                pass
            raise
        finally:
            elapsed = time.perf_counter() - started
            if elapsed > 30:
                logger.warning("slow tool call: %.1fs", elapsed)


# ---------------------------------------------------------------------------
# ASGI middleware: API-key auth for HTTP deployments
# ---------------------------------------------------------------------------

class ApiKeyASGIMiddleware:
    """Pure-ASGI bearer/X-API-key gate. When NAVIGATOR_API_KEYS is set, every
    request (except /health) must present one of the keys. Optional — use it
    whenever the HTTP endpoint is reachable beyond localhost."""

    def __init__(self, app, api_keys: set[str]) -> None:
        self.app = app
        self.api_keys = api_keys

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path.rstrip("/") == "/health":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        presented = headers.get("x-api-key", "")
        if not presented and headers.get("authorization", "").lower().startswith("bearer "):
            presented = headers["authorization"][7:].strip()
        if presented in self.api_keys:
            await self.app(scope, receive, send)
            return

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b'Bearer realm="navigator-mcp"'),
                ],
            }
        )
        body = json.dumps(
            {"error": "unauthorized", "hint": "send X-API-Key or Authorization: Bearer"}
        ).encode()
        await send({"type": "http.response.body", "body": body})


async def health_endpoint(request):
    from starlette.responses import JSONResponse

    runtime = get_runtime()
    return JSONResponse(
        {
            "status": "ok",
            "service": "navigator-mcp",
            "version": __version__,
            "sessions": len(runtime.browser.sessions),
        }
    )


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app=None):
    runtime = get_runtime()
    await runtime.start()
    logger.info(
        "Navigator runtime up (stealth=%s, humanize=%s)",
        runtime.settings.stealth,
        runtime.settings.humanize_input,
    )
    try:
        yield
    finally:
        await runtime.stop()
        logger.info("Navigator runtime down")


def build_server() -> FastMCP:
    """Create the FastMCP instance with instructions, middleware and tools."""
    mcp = FastMCP(
        name="Navigator MCP",
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
        middleware=[MeteringMiddleware()],
        lifespan=_lifespan,
    )
    register_tools(mcp)
    return mcp


def build_http_app():
    """Starlette app for HTTP deployment: MCP endpoint + API-key gate + /health."""
    from starlette.middleware import Middleware
    from starlette.routing import Route

    settings = get_settings()
    mcp = build_server()
    middlewares = []
    if settings.api_keys:
        middlewares.append(
            Middleware(ApiKeyASGIMiddleware, api_keys=set(settings.api_keys))
        )
        logger.info("HTTP API-key auth enabled (%d key(s))", len(settings.api_keys))
    app = mcp.http_app(path="/mcp", middleware=middlewares)
    try:
        app.router.routes.append(Route("/health", health_endpoint, methods=["GET"]))
    except Exception as exc:
        logger.debug("could not attach /health route: %s", exc)
    return app
