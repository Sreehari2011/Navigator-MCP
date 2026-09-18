# Navigator MCP — the pathfinding browser MCP

**High-performance browser automation for LLM agents.**
One Model Context Protocol server — the *Navigator*

- 🧠 **Token-efficient perception** — ref-based accessibility snapshots with
  change-caching (an unchanged page costs ~40 tokens, not 4,000)
- 🥷 **Advanced stealth** — coherent fingerprint profiles, runtime patches
  (WebGL/canvas/navigator/chrome), human-like mouse paths & typing jitter
- 🧩 **Captcha handling** — detection for 8+ providers, auto-solve via
  2Captcha/CapSolver, manual handoff with a visible browser
- 📡 **Traffic intelligence** — network capture/blocking, hidden API
  discovery, console & dialog observability
- 🗂 **Isolated sessions** — per-session fingerprint/proxy/cookies, auth
  persistence across restarts, up to 64 parallel sessions
- 🔓 **Zero gating** — no licenses, no tiers, no telemetry, no phone-home.
  Every capability is always unlocked; usage stats stay on your disk

> The VAPT security suite (OOB callbacks, passive scanning, WAF detection,
> raw HTTP, XSS probing) that shipped in v1.x has been **extracted to
> `reference/`** — proven, tested code parked for a dedicated **Security
> MCP** companion server. See `reference/README.md`.

```
51 tools · stdio + Streamable HTTP · Python 3.10+ · Playwright Chromium
```

---

## Why Navigator outperforms the field

| Capability | Playwright MCP | Browserbase | Stagehand | **Navigator** |
|---|:---:|:---:|:---:|:---:|
| Ref-based AX snapshots | ✅ | ✅ | ➖ | ✅ |
| **Snapshot change-caching** (unchanged page → 1-liner) | ❌ | ❌ | ❌ | ✅ |
| Auto-snapshot after actions (no extra round-trip) | partial | ❌ | ➖ | ✅ |
| Shadow-DOM traversal | ❌ | ❌ | partial | ✅ |
| Batch form filling (one call, N fields) | ❌ | ❌ | ❌ | ✅ |
| Advanced stealth (fingerprint + runtime + humanized input) | ❌ | partial | ❌ | ✅ |
| Captcha detect + auto-solve + manual handoff | ❌ | ❌ | ❌ | ✅ |
| Network capture / blocking / API discovery | partial | partial | ❌ | ✅ |
| Console & dialog capture (JS-error observability) | partial | ❌ | ❌ | ✅ |
| Isolated sessions with auth persistence | partial | ✅ | partial | ✅ |
| Optional navigation lockdown (domain allowlist) | ❌ | ❌ | ❌ | ✅ |
| "Pro" features behind a paywall | metered | ✅ | partial | **never** |
| Local-first, zero telemetry | ✅ | ❌ | ✅ | ✅ |

Numbers that matter for autonomous agents: on a typical multi-step task
(login → navigate → extract), change-caching + auto-snapshots + batch fill
cut **token usage by ~50–70%** and **round-trips by ~40%** vs a
snapshot-per-step loop.

---

## Quickstart

### Local (Claude Desktop / Cursor / VS Code / any MCP client)

```bash
pip install -e .
playwright install chromium
```

`claude_desktop_config.json` (see `examples/`):

```json
{
  "mcpServers": {
    "navigator": {
      "command": "navigator-mcp",
      "env": { "NAVIGATOR_STEALTH": "true" }
    }
  }
}
```

That's it. The first `browser_navigate` lazily starts a stealthed Chromium.

### Remote access (your own server, optional API keys)

```bash
NAVIGATOR_API_KEYS=sk-my-laptop,sk-my-desktop \
navigator-mcp --transport http --host 0.0.0.0 --port 8765
```

Clients connect to `http://your-host:8765/mcp` with header
`X-API-Key: sk-my-laptop`. Unauthenticated requests get `401`;
`GET /health` is open for monitoring.

### Docker

```bash
docker compose up                                   # HTTP on :8765
docker compose --profile vnc up                     # + headful VNC on :5901
docker run -i --rm --init navigator-mcp             # stdio for local clients
```

---

## The tool surface (51 tools)

**Perceive** — `browser_snapshot` (ref tree, change-cached, `deep=true` for
frames) · `browser_find` (regex search, actionable-first) ·
`browser_extract_text/html/links/forms/tables/meta` (paginated) ·
`browser_read_console` · `browser_read_dialogs`

**Act** — `browser_click` · `browser_click_text` · `browser_fill` ·
`browser_fill_form` (batch) · `browser_select_option` · `browser_hover` ·
`browser_press_key` · `browser_drag` · `browser_upload_file` ·
`browser_scroll` · `browser_wait_for`

**Navigate** — `browser_navigate` · `browser_navigate_back/forward` ·
`browser_reload` · `browser_get_url`

**Organize** — `browser_tab_list/new/select/close` ·
`browser_session_list/new/close/save_auth` (isolated contexts, persistent
auth profiles, per-session proxy/fingerprint/HAR recording)

**See** — `browser_screenshot` (native image content: viewport / full page /
element) · `browser_save_pdf`

**Inspect traffic** — `browser_network_capture_start/stop/list/get` ·
`browser_network_block/unblock` · `browser_discover_apis` (find the JSON
endpoints behind any page) · `browser_set_dialog_mode` ·
`browser_dialog_respond`

**Compute** — `browser_evaluate` (arbitrary JS, arg passing)

**Captchas** — `browser_captcha_detect` · `browser_captcha_solve`
(needs a provider key) · `browser_captcha_manual_wait`

**System** — `navigator_status` · `usage_report` (local stats)

### The core loop in practice

```
You:   Fill the login form on staging.acme.io and screenshot the dashboard.

Model: browser_navigate("https://staging.acme.io/login")
       → snapshot included automatically:
         - textbox "Email" [ref=e4]
         - textbox "Password" [ref=e5]
         - button "Sign in" [ref=e9]
       browser_fill_form([{ref: "e4", value: "bot@acme.io"},
                          {ref: "e5", value: "••••"}])
       browser_click(ref="e9")
       → new snapshot included (page changed)
       browser_screenshot(area="viewport")
```

Three tool calls, zero redundant snapshots, refs stable across steps.

---

## Stealth: what's actually patched

Per **session** (contexts never share fingerprints):

| Layer | Mechanism |
|---|---|
| Network | UA / `sec-ch-ua` / `sec-ch-ua-platform` / `accept-language` headers coherent with the chosen profile |
| Navigator | `webdriver` removed, `platform`, `languages`, `hardwareConcurrency`, `deviceMemory`, `plugins`/`mimeTypes` (5 realistic Chrome plugins), `maxTouchPoints` |
| `window.chrome` | `runtime` (ports + listeners), `app`, `loadTimes`, `csi` |
| WebGL | `UNMASKED_VENDOR/RENDERER` return profile-matched GPU strings |
| Canvas / Audio | session-stable deterministic noise (fingerprint distinct per session, consistent within it) |
| Input | Bézier mouse paths with overshoot+correction, typing jitter with occasional typo-and-fix, burst scrolling |
| Permissions | `Notification.permission`/`permissions.query` consistency |

Six bundled profiles (Win/Mac/Linux × Chrome/Safari) — or bring a patched
browser via `NAVIGATOR_CDP_ENDPOINT=ws://…` and Navigator drives it (Camoufox,
rebrowser-patches, your own build).

> For maximum anti-bot resilience run headful: `NAVIGATOR_HEADLESS=false`
> (locally) or the `vnc` compose profile (container). Headless Chrome has
> residual fingerprints no JS patch fully erases.

## Captcha flow

1. `browser_captcha_detect` → type + evidence + sitekeys
2. `browser_captcha_solve` → reCAPTCHA v2 / hCaptcha / Turnstile token
   solved by your 2Captcha or CapSolver key and injected; image captchas
   solved from an element screenshot; auto re-check
3. Manual fallback: headful browser + `browser_captcha_manual_wait` while a
   human solves it over VNC

---

## No licensing — everything unlocked

There is no license server, no key format, no tier table, no phone-home,
and nothing to configure. All 51 tools — stealth, captcha auto-solve,
unlimited sessions (resource-capped at 64 by default, raise via
`NAVIGATOR_MAX_SESSIONS`), the HTTP transport — are always available.

The only "metering" is a local stats file (`~/.navigator/usage.json`) that
powers the `usage_report` tool: per-tool counters, per-day breakdown,
and totals. **No URLs, no page content, nothing leaves your machine.**
Turn it off with `NAVIGATOR_STATS=false` if even that is unwanted.

When you expose the HTTP transport beyond localhost, set `NAVIGATOR_API_KEYS`
to require bearer keys — that's plain access control for your own endpoint,
not a billing feature.

---

## Configuration reference

Everything is environment-driven (see `.env.example` for the full list):

| Variable | Default | Purpose |
|---|---|---|
| `NAVIGATOR_HEADLESS` | `true` | headless mode (set false for captchas/anti-bot) |
| `NAVIGATOR_STEALTH` | `true` | fingerprint + runtime patches |
| `NAVIGATOR_HUMANIZE` | `true` | human-like input synthesis |
| `NAVIGATOR_AUTO_SNAPSHOT` | `true` | include snapshots in action results |
| `NAVIGATOR_MAX_SESSIONS` | `64` | resource cap on parallel sessions |
| `NAVIGATOR_CDP_ENDPOINT` | – | drive an external (patched) browser |
| `NAVIGATOR_PROXY_SERVER` | – | default proxy for all sessions |
| `NAVIGATOR_ALLOWED_DOMAINS` | – | optional navigation lockdown (allowlist) |
| `NAVIGATOR_API_KEYS` | – | HTTP auth keys (comma-separated) |
| `NAVIGATOR_STATS` | `true` | local usage counters for usage_report |
| `TWOCAPTCHA_API_KEY` / `CAPSOLVER_API_KEY` | – | captcha provider keys |

## Architecture

```
navigator_mcp/
├── server.py            FastMCP assembly · instructions · stats middleware
├── __main__.py          CLI: stdio / http
├── config.py            env-driven settings
├── metering.py          purely local usage counters
├── runtime.py           singleton wiring · navigation lockdown · session cap
├── core/
│   ├── browser.py       sessions · tabs · per-page event wiring
│   └── scope.py         optional domain-allowlist lockdown
├── perception/
│   ├── snapshot.py      ref-based AX collector (shadow DOM, frames) + renderer
│   └── extraction.py    text/html/links/forms/tables/meta
├── stealth/
│   ├── fingerprints.py  coherent profile bundles
│   ├── init_scripts.py  per-session runtime patches (JS)
│   └── humanize.py      Bézier mouse · typing jitter · burst scroll
├── captcha/
│   ├── detector.py      8+ captcha families, sitekey discovery
│   └── providers.py     2Captcha + CapSolver async clients
└── network/
    └── interceptor.py   capture filters · API discovery

```

## Development

```bash
pip install -e ".[dev]"
playwright install chromium      # for browser-marked tests + the E2E script
./scripts/run_checks.sh          # one command: lint + pytest + real-browser E2E + HTTP smoke
./scripts/run_checks.sh --fast   # lint + pytest only (no browser, no server)
```

`pytest` runs 28 tests (browser-marked ones auto-skip without a chromium
binary). The two E2E scripts can also be run individually:
`python scripts/e2e_browser.py` (9-check live browser loop) and
`python scripts/http_smoke.py` (boots the HTTP server, checks the API-key
gate and the MCP initialize handshake).

## Roadmap

- Firefox/WebKit session engines · cookie-jar import/export
- Remote browser grid (connect a fleet via CDP endpoints)
- Playwright-element-handle-compatible script recording
- Headful farm orchestration on top of the VNC profile
