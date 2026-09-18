"""Full-stack integration test (requires the chromium binary).

Verifies: lazy default session, stealth patches, snapshot refs, humanized
interaction, console capture, ref stability, navigation lockdown at tool level.
"""

import re

import pytest
from conftest import requires_browser
from fastmcp.exceptions import ToolError


@pytest.fixture
async def client():
    from fastmcp import Client

    from navigator_mcp.server import build_server

    mcp = build_server()
    async with Client(mcp) as c:
        yield c
    from navigator_mcp.runtime import get_runtime

    await get_runtime().browser.stop()


TEST_HTML = """<!DOCTYPE html>
<html><head><title>Integration Test</title></head><body>
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


@requires_browser
async def test_full_flow(tmp_path, client):
    page_file = tmp_path / "t.html"
    page_file.write_text(TEST_HTML)

    # 1. lazy default session: navigate is the first-ever call
    r = await client.call_tool("browser_navigate", {"url": f"file://{page_file}"})
    nav = r.content[0].text
    assert "Navigated" in nav

    # 2. snapshot with refs included in navigate result
    assert "textbox" in nav and "[ref=" in nav

    # 3. cached snapshot
    r = await client.call_tool("browser_snapshot", {})
    assert "unchanged" in r.content[0].text

    # 4. stealth applied
    from navigator_mcp.runtime import get_runtime

    ps = get_runtime().browser.get_page("default")
    webdriver = await ps.page.evaluate("() => navigator.webdriver")
    assert webdriver is None or webdriver is False
    plugins = await ps.page.evaluate("() => navigator.plugins.length")
    assert plugins >= 3

    # 5. find + fill + click
    r = await client.call_tool("browser_find", {"pattern": "search", "role": "textbox"})
    ref = re.search(r"\[ref=(e\d+)\]", r.content[0].text).group(1)
    await client.call_tool("browser_fill", {"ref": ref, "text": "hello"})
    value = await ps.page.evaluate("() => document.getElementById('q').value")
    assert value == "hello"

    r = await client.call_tool("browser_find", {"pattern": "^go$"})
    btn_ref = re.search(r"\[ref=(e\d+)\]", r.content[0].text).group(1)
    await client.call_tool("browser_click", {"ref": btn_ref})

    # 6. console error captured
    r = await client.call_tool("browser_read_console", {"n": 5})
    assert "triggered" in r.content[0].text

    # 7. navigation lockdown (NAVIGATOR_ALLOWED_DOMAINS policy scope)
    from navigator_mcp.runtime import get_runtime

    get_runtime().scope.set_policy(["allowed.com"])
    with pytest.raises(ToolError):
        await client.call_tool("browser_navigate", {"url": "https://evil.example.com"})
    get_runtime().scope.set_policy([])


@requires_browser
async def test_sessions_and_screenshot(client):
    await client.call_tool("browser_session_new", {"name": "alt"})
    r = await client.call_tool("browser_session_list", {})
    assert "alt" in r.content[0].text
    r = await client.call_tool(
        "browser_screenshot", {"format": "jpeg", "quality": 40, "session": "alt"}
    )
    assert any("Image" in type(c).__name__ for c in r.content)
    await client.call_tool("browser_session_close", {"name": "alt"})
