"""Snapshot rendering, hashing and ref parsing (no browser needed)."""

from navigator_mcp.perception.snapshot import (
    parse_ref,
    render_snapshot,
    snapshot_hash,
)

RAW = {
    "url": "https://example.com/page",
    "title": "Example",
    "scrollY": 0,
    "scrollHeight": 1200,
    "viewport": {"w": 1440, "h": 900},
    "nodeCount": 4,
    "truncated": False,
    "nodes": [
        {"ref": "e1", "role": "banner", "name": "", "depth": 0, "states": []},
        {"ref": "e2", "role": "heading", "name": "Hello World", "depth": 1,
         "states": ["level=1"]},
        {"ref": "e3", "role": "textbox", "name": 'Search "quoted"', "depth": 1,
         "states": ["required", 'value="abc"']},
        {"ref": "e4", "role": "link", "name": "Next", "depth": 1, "states": []},
    ],
    "textBlocks": ["Some text"],
    "frames": [],
}


def test_render_contains_all_elements():
    text = render_snapshot(RAW)
    assert '# URL: https://example.com/page' in text
    assert '- heading "Hello World" [level=1] [ref=e2]' in text
    assert '- textbox "Search \'quoted\'" [required] [value="abc"] [ref=e3]' in text
    assert '- link "Next" [ref=e4]' in text
    assert '- text "Some text"' in text


def test_render_truncation_notice():
    raw = dict(RAW, truncated=True)
    assert "snapshot truncated" in render_snapshot(raw)


def test_hash_stability_and_sensitivity():
    h1 = snapshot_hash(RAW)
    h2 = snapshot_hash(dict(RAW))  # same content
    assert h1 == h2

    changed = dict(RAW)
    changed = {
        **RAW,
        "nodes": RAW["nodes"][:-1],  # element removed
    }
    assert snapshot_hash(changed) != h1

    # scroll position is part of the hash (viewport content changes)
    scrolled = {**RAW, "scrollY": 400}
    assert snapshot_hash(scrolled) != h1


def test_parse_ref():
    assert parse_ref("e12") == (None, '[data-navigator-ref="e12"]')
    assert parse_ref("f2!e5") == (2, '[data-navigator-ref="e5"]')
    assert parse_ref("  e7 ") == (None, '[data-navigator-ref="e7"]')


def test_quotes_sanitized():
    raw = {
        **RAW,
        "nodes": [{"ref": "e1", "role": "button", "name": 'He said "hi"',
                   "depth": 0, "states": []}],
    }
    text = render_snapshot(raw)
    assert '"hi"' not in text  # double quotes replaced
    assert "He said 'hi'" in text
