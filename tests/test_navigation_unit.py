"""URL sanitization in navigation tools (no browser needed)."""

import pytest
from fastmcp.exceptions import ToolError

from navigator_mcp.tools.navigation import _sanitize_url


def test_schemeless_gets_https():
    assert _sanitize_url("example.com") == "https://example.com"
    assert _sanitize_url("example.com:8080/path") == "https://example.com:8080/path"
    assert _sanitize_url(' "example.com" ') == "https://example.com"


def test_full_schemes_kept():
    assert _sanitize_url("http://x.test") == "http://x.test"
    assert _sanitize_url("https://x.test/a?b=c") == "https://x.test/a?b=c"
    assert _sanitize_url("file:///tmp/page.html") == "file:///tmp/page.html"
    assert _sanitize_url("ws://127.0.0.1:9222/playwright") == "ws://127.0.0.1:9222/playwright"


def test_bare_schemes_not_mangled():
    assert _sanitize_url("about:blank") == "about:blank"
    assert _sanitize_url("data:text/html,<h1>hi</h1>") == "data:text/html,<h1>hi</h1>"
    assert _sanitize_url("view-source:https://x.test") == "view-source:https://x.test"
    assert _sanitize_url("mailto:a@b.test") == "mailto:a@b.test"
    assert _sanitize_url("blob:https://x.test/uuid") == "blob:https://x.test/uuid"


def test_empty_rejected():
    with pytest.raises(ToolError):
        _sanitize_url("")
    with pytest.raises(ToolError):
        _sanitize_url("   ")
