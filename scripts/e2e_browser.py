"""E2E: full browser loop on Navigator MCP with a real Chromium.

Covers: status shape, navigate→snapshot→find→fill→click→console, snapshot
caching, captcha tool reachability, parallel sessions, navigation lockdown,
and JS evaluation. Requires a Playwright chromium binary
(``playwright install chromium``).

Run directly (``python scripts/e2e_browser.py``) or via ``scripts/run_checks.sh``.
"""

import asyncio
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import Client

from navigator_mcp.server import build_server

TEST_HTML = """<!DOCTYPE html>
<html><head><title>E2E Browser</title></head><body>
<main>
  <h1>Form Demo</h1>
  <form>
    <input id="q" name="q" type="text" placeholder="Search...">
    <button type="button" id="go" onclick="console.error('triggered')">Go</button>
  </form>
  <a href="/link1">First Link</a>
  <p>Paragraph text for context.</p>
</main>
</body></html>"""


async def main(tmpdir: str) -> None:
    page_file = f"{tmpdir}/e2e.html"
    with open(page_file, "w") as fh:
        fh.write(TEST_HTML)

    mcp = build_server()
    async with Client(mcp) as c:
        # 1. status: browser-only shape
        r = await c.call_tool("navigator_status", {})
        status = r.content[0].text
        assert "all unlocked" in status
        assert "navigation_lockdown" in status and "security" not in status.lower()
        print("[1] navigator_status: browser-only, all unlocked")

        # 2. navigate (lazy default session) with embedded snapshot
        r = await c.call_tool("browser_navigate", {"url": f"file://{page_file}"})
        nav = r.content[0].text
        assert "Navigated" in nav and "[ref=" in nav and "textbox" in nav
        print("[2] navigate -> snapshot with refs (lazy default session)")

        # 3. snapshot cache: unchanged page
        r = await c.call_tool("browser_snapshot", {})
        assert "unchanged" in r.content[0].text
        print("[3] snapshot caching works")

        # 4. find + fill + click + console
        r = await c.call_tool("browser_find", {"pattern": "search"})
        ref = re.search(r"\[ref=(e\d+)\]", r.content[0].text).group(1)
        await c.call_tool("browser_fill", {"ref": ref, "text": "hello"})
        r = await c.call_tool("browser_find", {"pattern": "^go$"})
        btn = re.search(r"\[ref=(e\d+)\]", r.content[0].text).group(1)
        await c.call_tool("browser_click", {"ref": btn})
        r = await c.call_tool("browser_read_console", {"n": 5})
        assert "triggered" in r.content[0].text
        print("[4] find -> fill -> click -> console capture")

        # 5. extract links
        r = await c.call_tool("browser_extract_links", {})
        assert "link1" in r.content[0].text
        print("[5] extraction tools")

        # 6. captcha tools reachable (no captcha -> polite message)
        r = await c.call_tool("browser_captcha_detect", {})
        assert "captcha_present" in r.content[0].text
        r = await c.call_tool("browser_captcha_solve", {})
        assert "No captcha detected" in r.content[0].text
        print("[6] captcha detect + solve paths reachable")

        # 7. parallel sessions + tabs
        await c.call_tool("browser_session_new", {"name": "s2"})
        await c.call_tool("browser_tab_new", {"session": "s2"})
        r = await c.call_tool("browser_session_list", {})
        assert "s2" in r.content[0].text
        print("[7] parallel sessions + tabs")

        # 8. navigation lockdown (NAVIGATOR_ALLOWED_DOMAINS policy)
        from navigator_mcp.runtime import get_runtime

        get_runtime().scope.set_policy(["allowed.com"])
        try:
            await c.call_tool("browser_navigate", {"url": "https://evil.example.com"})
            raise AssertionError("lockdown did not block")
        except Exception as exc:
            assert "NAVIGATION BLOCKED" in str(exc), exc
        get_runtime().scope.set_policy([])
        print("[8] navigation lockdown enforced + cleared "
              "(the 'Error calling tool browser_navigate' log line above is the "
              "expected block — that's the test succeeding)")

        # 9. evaluate JS
        r = await c.call_tool(
            "browser_evaluate", {"expression": "() => 6 * 7"}
        )
        assert "42" in r.content[0].text
        print("[9] browser_evaluate")

    from navigator_mcp.runtime import get_runtime

    await get_runtime().browser.stop()
    print("\nALL E2E CHECKS PASSED — pure browser MCP, every advanced feature intact.")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        asyncio.run(main(td))
