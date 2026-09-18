"""Playwright browser runtime: sessions, tabs, and per-page state wiring.

A **session** is an isolated browser context (own cookies, storage, fingerprint
and optional proxy) — the unit of isolation for multi-tenant or multi-task use.
Each session owns one or more **tabs** (pages). Every page gets automatic
wiring for console capture, dialog capture (auto-accept or manual), network
capture, and popup handling — the observation layer every Navigator tool and the
LLM perception layer both build on.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Dialog,
    Download,
    Page,
    Playwright,
    Request,
    Response,
    async_playwright,
)

from ..config import Settings
from ..stealth.fingerprints import Fingerprint, pick_fingerprint
from ..stealth.init_scripts import build_stealth_script

logger = logging.getLogger("navigator.browser")

MAX_CONSOLE = 200
MAX_DIALOGS = 50
MAX_REQUESTS = 400


@dataclass
class NetworkEntry:
    index: int
    method: str
    url: str
    resource_type: str
    ts: float
    request_headers: dict[str, str] = field(default_factory=dict)
    post_data: str | None = None
    status: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    # Transient handles (not serialized; used for on-demand body fetch)
    _response: Any | None = field(default=None, repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "method": self.method,
            "url": self.url,
            "resource_type": self.resource_type,
            "status": self.status,
            "post_data": (self.post_data[:300] if self.post_data else None),
        }


@dataclass
class PageState:
    page: Page
    created_at: float = field(default_factory=time.time)
    console: deque = field(default_factory=lambda: deque(maxlen=MAX_CONSOLE))
    page_errors: deque = field(default_factory=lambda: deque(maxlen=50))
    dialogs: deque = field(default_factory=lambda: deque(maxlen=MAX_DIALOGS))
    requests: deque = field(default_factory=lambda: deque(maxlen=MAX_REQUESTS))
    downloads: deque = field(default_factory=lambda: deque(maxlen=20))
    dialog_mode: str = "auto"  # "auto" (accept+record) | "manual"
    pending_dialog: Dialog | None = field(default=None, repr=False)
    network_capture: bool = False
    capture_filter: dict[str, Any] = field(default_factory=dict)
    last_document_response: dict[str, Any] | None = None  # main-frame doc
    _req_counter: int = 0
    last_snapshot_text: str = ""
    last_snapshot_hash: str = ""
    snapshot_count: int = 0

    # ------------------------------------------------------------------ console

    def console_tail(self, n: int = 20) -> list[str]:
        return list(self.console)[-n:]

    def drain_console(self) -> list[str]:
        out = list(self.console)
        self.console.clear()
        return out

    # ------------------------------------------------------------------ dialogs

    def dialog_tail(self, n: int = 10) -> list[dict]:
        return list(self.dialogs)[-n:]

    # ------------------------------------------------------------------ network

    def _filter_ok(self, method: str, url: str, resource_type: str) -> bool:
        flt = self.capture_filter or {}
        if flt.get("methods") and method.upper() not in flt["methods"]:
            return False
        if flt.get("resource_types") and resource_type not in flt["resource_types"]:
            return False
        pat = flt.get("url_contains")
        if pat and pat.lower() not in url.lower():
            return False
        return True

    def network_list(self, n: int = 30, statuses: list[int] | None = None) -> list[dict]:
        out = []
        for entry in reversed(self.requests):
            if statuses and entry.status not in statuses:
                continue
            out.append(entry.summary())
            if len(out) >= n:
                break
        return out

    async def network_body(self, index: int) -> dict[str, Any]:
        for entry in self.requests:
            if entry.index == index:
                if entry._response is None:
                    return {"error": f"no stored response for request #{index}"}
                try:
                    body = await entry._response.body()
                except Exception as exc:
                    return {"error": f"body unavailable: {exc}"}
                text = body.decode("utf-8", errors="replace")
                return {
                    "index": index,
                    "url": entry.url,
                    "status": entry.status,
                    "headers": entry.response_headers,
                    "body": text,
                }
        return {"error": f"request #{index} not found in capture buffer"}


@dataclass
class Session:
    name: str
    context: BrowserContext
    pages: list[PageState] = field(default_factory=list)
    active_index: int = 0
    fingerprint: Fingerprint | None = None
    stealth: bool = True
    humanize: bool = True
    proxy: str | None = None
    created_at: float = field(default_factory=time.time)

    @property
    def active(self) -> PageState:
        if not self.pages:
            raise RuntimeError(f"session '{self.name}' has no open tabs")
        return self.pages[min(self.active_index, len(self.pages) - 1)]

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tabs": len(self.pages),
            "active_tab": self.active_index,
            "stealth": self.stealth,
            "humanize": self.humanize,
            "fingerprint": self.fingerprint.name if self.fingerprint else None,
            "proxy": self.proxy,
            "urls": [p.page.url for p in self.pages],
        }


class BrowserRuntime:
    """Owns the Playwright driver and all sessions."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self.sessions: dict[str, Session] = {}
        self._blocked_routes: list[str] = []
        self._background_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        if self._playwright is not None:
            return
        self._playwright = await async_playwright().start()
        logger.info("playwright driver started")

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError(
                "browser not launched yet — call ensure_session() first "
                "or use a navigation tool to lazily start it"
            )
        return self._browser

    async def _launch_browser(self) -> Browser:
        assert self._playwright is not None, "runtime not started"
        if self.settings.cdp_endpoint:
            logger.info("connecting over CDP: %s", self.settings.cdp_endpoint)
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self.settings.cdp_endpoint
            )
            return self._browser
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--window-size=1600,1000",
        ]
        kwargs: dict[str, Any] = {"args": launch_args}
        if self.settings.browser_channel and self.settings.browser_channel != "chromium":
            kwargs["channel"] = self.settings.browser_channel
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.headless, **kwargs
        )
        return self._browser

    async def stop(self) -> None:
        for name in list(self.sessions):
            await self.close_session(name, from_shutdown=True)
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:
                logger.debug("browser close error: %s", exc)
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.debug("playwright stop error: %s", exc)
            self._playwright = None
        logger.info("browser runtime stopped")

    # ------------------------------------------------------------------ sessions

    async def ensure_session(self, name: str = "default") -> Session:
        if name in self.sessions:
            return self.sessions[name]
        return await self.create_session(name)

    async def create_session(
        self,
        name: str,
        *,
        stealth: bool = True,
        proxy: str | None = None,
        storage_state: str | None = None,
        record_har: str | None = None,
        fingerprint_name: str | None = None,
        locale: str | None = None,
        timezone: str | None = None,
        geolocation: dict | None = None,
        extra_headers: dict[str, str] | None = None,
        bypass_csp: bool = False,
        user_agent: str | None = None,
    ) -> Session:
        await self.start()
        if self._browser is None:
            await self._launch_browser()

        fingerprint = pick_fingerprint(fingerprint_name) if stealth else None
        if user_agent and fingerprint:
            fingerprint = fingerprint.with_overrides(user_agent=user_agent)
        elif user_agent:
            fingerprint = Fingerprint.minimal(user_agent)

        effective_proxy = proxy or (self.settings.proxy_server or None)
        ctx_kwargs: dict[str, Any] = {
            "ignore_https_errors": True,
            "bypass_csp": bypass_csp,
            "service_workers": "allow",
        }
        if fingerprint:
            ctx_kwargs.update(fingerprint.context_kwargs())
        else:
            ctx_kwargs["viewport"] = {
                "width": self.settings.default_viewport_width,
                "height": self.settings.default_viewport_height,
            }
        if locale:
            ctx_kwargs["locale"] = locale
        if timezone:
            ctx_kwargs["timezone_id"] = timezone
        if geolocation:
            ctx_kwargs["geolocation"] = geolocation
        if extra_headers:
            ctx_kwargs["extra_http_headers"] = extra_headers
        if effective_proxy:
            ctx_kwargs["proxy"] = {"server": effective_proxy}
        if storage_state:
            ctx_kwargs["storage_state"] = storage_state
        if record_har:
            ctx_kwargs["record_har_path"] = record_har

        context = await self.browser.new_context(**ctx_kwargs)
        context.set_default_navigation_timeout(self.settings.navigation_timeout_ms)
        context.set_default_timeout(self.settings.action_timeout_ms)

        if stealth and fingerprint:
            await context.add_init_script(build_stealth_script(fingerprint))

        session = Session(
            name=name,
            context=context,
            fingerprint=fingerprint,
            stealth=stealth,
            humanize=self.settings.humanize_input,
            proxy=effective_proxy,
        )
        self.sessions[name] = session

        page = await context.new_page()
        self._wire_page(session, page)
        # Re-apply blocking rules to contexts created later
        if self._blocked_routes:
            await self._apply_routes(context)
        logger.info("session '%s' created (stealth=%s)", name, stealth)
        return session

    async def close_session(self, name: str, *, from_shutdown: bool = False) -> None:
        session = self.sessions.pop(name, None)
        if session is None:
            raise KeyError(f"session '{name}' not found")
        try:
            await session.context.close()
        except Exception as exc:
            if not from_shutdown:
                logger.debug("context close error: %s", exc)
        logger.info("session '%s' closed", name)

    def get_session(self, name: str = "default") -> Session:
        session = self.sessions.get(name)
        if session is None:
            raise KeyError(
                f"session '{name}' not found. Active sessions: "
                f"{sorted(self.sessions) or 'none'}. "
                f"Create one with browser_session_new()."
            )
        return session

    def session_infos(self) -> list[dict[str, Any]]:
        return [s.info() for s in self.sessions.values()]

    # ------------------------------------------------------------------ tabs

    async def new_tab(self, session_name: str, url: str | None = None) -> PageState:
        session = self.get_session(session_name)
        page = await session.context.new_page()
        ps = self._wire_page(session, page)
        session.active_index = len(session.pages) - 1
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        return ps

    async def close_tab(self, session_name: str, index: int) -> None:
        session = self.get_session(session_name)
        if len(session.pages) <= 1:
            raise ValueError("cannot close the last tab of a session")
        if not 0 <= index < len(session.pages):
            raise IndexError(f"tab index {index} out of range (0..{len(session.pages) - 1})")
        ps = session.pages.pop(index)
        try:
            await ps.page.close()
        except Exception as exc:
            logger.debug("page close error: %s", exc)
        if session.active_index >= len(session.pages):
            session.active_index = len(session.pages) - 1

    def get_page(self, session_name: str = "default", tab: int | None = None) -> PageState:
        session = self.get_session(session_name)
        if tab is None:
            return session.active
        if not 0 <= tab < len(session.pages):
            raise IndexError(
                f"tab index {tab} out of range (0..{len(session.pages) - 1})"
            )
        return session.pages[tab]

    # ------------------------------------------------------------------ auth persistence

    async def save_auth(self, session_name: str, profile_name: str) -> str:
        session = self.get_session(session_name)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in profile_name)
        path = str(self.settings.profiles_dir / f"{safe}.json")
        await session.context.storage_state(path=path)
        logger.info("session '%s' auth state saved to %s", session_name, path)
        return path

    def storage_path_for(self, profile_name: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in profile_name)
        return str(self.settings.profiles_dir / f"{safe}.json")

    # ------------------------------------------------------------------ blocking

    async def block_urls(self, url_globs: list[str]) -> None:
        self._blocked_routes = list(dict.fromkeys(url_globs))
        for session in self.sessions.values():
            await self._apply_routes(session.context)

    async def clear_blocked_urls(self) -> None:
        for session in self.sessions.values():
            try:
                await session.context.unroute("**/*")
            except Exception:
                pass
        self._blocked_routes = []

    async def _apply_routes(self, context: BrowserContext) -> None:
        try:
            await context.unroute("**/*")
        except Exception:
            pass
        if not self._blocked_routes:
            return

        async def _handler(route: Any) -> None:
            await route.abort()

        for pattern in self._blocked_routes:
            try:
                await context.route(pattern, _handler)
            except Exception as exc:
                logger.warning("could not register block pattern %r: %s", pattern, exc)

    # ------------------------------------------------------------------ wiring

    def _wire_page(self, session: Session, page: Page) -> PageState:
        ps = PageState(page=page)
        session.pages.append(ps)

        def _on_console(msg: Any) -> None:
            try:
                ps.console.append(f"[{msg.type}] {msg.text}")
                if len(ps.console) > MAX_CONSOLE:
                    ps.console.popleft()
            except Exception:
                pass

        def _on_page_error(err: Any) -> None:
            try:
                ps.page_errors.append(str(err)[:500])
            except Exception:
                pass

        def _on_dialog(dialog: Dialog) -> None:
            record = {
                "type": dialog.type,
                "message": dialog.message[:500],
                "ts": time.time(),
                "handled": ps.dialog_mode == "auto",
            }
            ps.dialogs.append(record)
            if ps.dialog_mode == "auto":
                task = asyncio.ensure_future(self._safe_accept(dialog))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            else:
                ps.pending_dialog = dialog

        def _on_request(request: Request) -> None:
            try:
                if not ps.network_capture:
                    return
                rtype = request.resource_type or "other"
                if not ps._filter_ok(request.method, request.url, rtype):
                    return
                ps._req_counter += 1
                post = request.post_data
                if post and len(post) > 4000:
                    post = post[:4000] + "…[truncated]"
                ps.requests.append(
                    NetworkEntry(
                        index=ps._req_counter,
                        method=request.method,
                        url=request.url,
                        resource_type=rtype,
                        ts=time.time(),
                        request_headers=dict(request.headers),
                        post_data=post,
                    )
                )
            except Exception:
                pass

        def _on_response(response: Response) -> None:
            try:
                # Track the main document response (always, even without capture)
                if response.request.resource_type == "document":
                    ps.last_document_response = {
                        "url": response.url,
                        "status": response.status,
                        "headers": dict(response.headers),
                        "ts": time.time(),
                        "_handle": response,
                    }
                if not ps.network_capture:
                    return
                req = response.request
                for entry in reversed(ps.requests):
                    if entry.url == req.url and entry.status is None:
                        entry.status = response.status
                        entry.response_headers = dict(response.headers)
                        entry._response = response
                        break
            except Exception:
                pass

        def _on_popup(popup: Page) -> None:
            popup_ps = self._wire_page(session, popup)
            session.active_index = len(session.pages) - 1
            logger.debug("popup attached as tab %d", session.active_index)
            return popup_ps

        def _on_download(download: Download) -> None:
            ps.downloads.append(
                {"url": download.url, "suggested_filename": download.suggested_filename,
                 "ts": time.time(), "_handle": download}
            )

        page.on("console", _on_console)
        page.on("pageerror", _on_page_error)
        page.on("dialog", _on_dialog)
        page.on("request", _on_request)
        page.on("response", _on_response)
        page.on("popup", _on_popup)
        page.on("download", _on_download)
        return ps

    @staticmethod
    async def _safe_accept(dialog: Dialog) -> None:
        try:
            await dialog.accept()
        except Exception as exc:
            logger.debug("dialog accept error: %s", exc)

    # ------------------------------------------------------------------ helpers

    async def settle(self, ps: PageState, *, wait_network_idle: bool = False) -> None:
        """Give SPAs a moment to re-render after an action."""
        try:
            await ps.page.wait_for_load_state("domcontentloaded", timeout=2000)
        except Exception:
            pass
        if wait_network_idle:
            try:
                await ps.page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass
        await asyncio.sleep(self.settings.settle_delay_ms / 1000)
