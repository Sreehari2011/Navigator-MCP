"""Fingerprint coherence + stealth script generation."""

import json
import re

import pytest

from navigator_mcp.stealth.fingerprints import (
    FINGERPRINTS,
    pick_fingerprint,
)
from navigator_mcp.stealth.init_scripts import build_stealth_script


def test_all_fingerprints_coherent():
    for fp in FINGERPRINTS:
        # platform must agree with the UA string
        if "Windows NT" in fp.user_agent:
            assert fp.platform == "Win32"
        elif "Macintosh" in fp.user_agent:
            assert fp.platform == "MacIntel"
        elif "Linux x86_64" in fp.user_agent:
            assert fp.platform == "Linux x86_64"
        else:
            pytest.fail(f"unknown platform in {fp.name}")
        # sec-ch-ua brand must agree with the UA Chrome major version
        if "Chrome/" in fp.user_agent:
            major = re.search(r"Chrome/(\d+)", fp.user_agent).group(1)
            assert f'v="{major}"' in fp.sec_ch_ua, fp.name
        # viewport must fit inside screen
        assert fp.viewport["width"] <= fp.screen["width"], fp.name
        assert fp.viewport["height"] <= fp.screen["height"], fp.name


def test_context_kwargs_shape():
    fp = FINGERPRINTS[0]
    kwargs = fp.context_kwargs()
    assert kwargs["user_agent"] == fp.user_agent
    assert kwargs["viewport"] == fp.viewport
    assert kwargs["timezone_id"] == fp.timezone
    assert kwargs["extra_http_headers"]["sec-ch-ua"] == fp.sec_ch_ua
    assert kwargs["extra_http_headers"]["sec-ch-ua-platform"] == "Windows"


def test_pick_by_name_and_unknown():
    assert pick_fingerprint("mac-safari-17").name == "mac-safari-17"
    with pytest.raises(ValueError):
        pick_fingerprint("nope")


def test_overrides():
    fp = FINGERPRINTS[0].with_overrides(user_agent="UA/Test")
    assert fp.user_agent == "UA/Test"
    assert fp.locale == FINGERPRINTS[0].locale


def test_stealth_script_contains_cfg():
    fp = FINGERPRINTS[0]
    script = build_stealth_script(fp)
    # config injected
    assert '"platform": "Win32"' in script
    assert json.dumps(fp.webgl_vendor) in script
    # key patches present
    for marker in (
        "navigator.webdriver",
        "getParameter",
        "toDataURL",
        "chrome.runtime",
        "plugins",
    ):
        assert marker in script, marker
    # it is a valid IIFE
    assert script.strip().startswith("(") and script.strip().endswith(");")
