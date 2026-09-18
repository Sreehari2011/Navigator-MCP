# Parked: the security suite (for the future Security MCP)

This directory preserves the **proven, tested security engine** that shipped
with the v1.x releases of this project — untouched, ready to be revived as a
dedicated **Security MCP** server. This project is now a pure browser MCP;
these files are *not* installed with the package and are excluded from
lint/test runs.

## What's here

| File | What it was | Lines of value |
|---|---|---|
| `oob.py` | Encrypted Interactsh client — OOBManager + OOBSession: RSA/AES payload decryption, blind-callback polling, payload-domain generation | async port of Hypervisor's engine |
| `passive.py` | Passive scanner — header/cookie flags, secret detection with entropy checks (AWS/Google/Slack/GitHub/Stripe/JWT/private keys), leaks, internal IPs, SQL errors, stack traces | pure functions, zero deps |
| `waf.py` | WAF fingerprinting — 10 header signatures + optional wafw00f thread bridge | pure + optional dep |
| `http_client.py` | Raw HTTP client — method/headers/body/cookies control, redirect-chain tracing, timing, auto passive scan of responses | httpx-based |
| `security_tools.py` | The 8 MCP tool wrappers that exposed the above (scan_page, detect_waf, set_scope, http_request, oob_generate/poll/reset, test_xss) | FastMCP tool bodies |
| `test_passive.py` / `test_waf.py` / `test_oob.py` | The unit tests that covered them (OOB tests now import from the local `oob` module) | keep them green when porting |

## Revival notes for the Security MCP

1. **Wiring**: `security_tools.py` imported shared helpers from Navigator
   (`._base.rt / page_for / ref_locator / require_visible / json_safe`,
   `..runtime` for the OOB manager, `..config` for `oob_server` /
   `oob_poll_url` / `http_verify_tls`). Recreate thin equivalents in the new
   server, or run it *alongside* Navigator and reach pages via Navigator itself.
2. **The XSS probe needs a live page** (`security_test_xss` fills a field by
   ref, then watches dialogs/console/DOM). Two options: give the Security MCP
   its own Playwright runtime, or make it a client of the Navigator MCP.
3. **Scope guard**: Navigator kept only the *policy* scope
   (`NAVIGATOR_ALLOWED_DOMAINS`) for browser navigation lockdown. The
   *engagement* scope concept (set before testing, subdomain-inclusive
   matching — see the old `core/scope.py` history) belongs to the Security
   MCP; reimplement it there and make it mandatory before any active tool.
4. **Dependencies**: `httpx` (required), `cryptography` (OOB decryption),
   `wafw00f` (optional WAF boost), `fastmcp`.
5. **Design that paid off**: OOB polling decrypts server-side ciphertext with
   a per-session RSA key — the Interactsh server never sees plaintext.
   Keep that property in the port.

The old tests are a faithful specification: if the port passes
`test_passive.py`, `test_waf.py` and `test_oob.py`, the engine survived
transplant.
