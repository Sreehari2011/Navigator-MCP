"""Shared fixtures. Browser-dependent tests are marked and auto-skipped."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                b = p.chromium.launch(headless=True)
                b.close()
                return True
            except Exception:
                return False
    except Exception:
        return False


HAS_BROWSER = _browser_available()
requires_browser = pytest.mark.skipif(
    not HAS_BROWSER, reason="Playwright chromium not installed (mark: browser)"
)


@pytest.fixture(autouse=True)
def _isolated_workspace(tmp_path, monkeypatch):
    """Keep tests away from the user's real ~/.navigator workspace."""
    monkeypatch.setenv("NAVIGATOR_WORKSPACE", str(tmp_path / "ws"))
    from navigator_mcp.config import reset_settings

    reset_settings()
    yield
    from navigator_mcp.runtime import reset_runtime

    reset_runtime()
    reset_settings()
