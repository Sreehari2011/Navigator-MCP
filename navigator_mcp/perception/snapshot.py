"""Ref-based accessibility snapshot — how the LLM sees the page.

Design (the part that makes Navigator fast and cheap to run):

* **Stable refs** — every interactive element gets a ``data-navigator-ref``
  attribute (``e1``, ``e2``, …). Refs survive re-snapshots: unchanged
  elements keep their ref, so the LLM can keep using ``ref=e12`` across
  steps without re-reading the whole page.
* **Compact YAML-ish rendering** — structural wrappers are collapsed; only
  interactive elements, headings, images and text blocks are emitted.
* **Hash-based caching** — each snapshot is hashed; if nothing changed the
  tool returns a one-liner instead of re-sending the tree (huge token win on
  multi-step flows).
* **Shadow DOM piercing** — custom elements with shadow roots are traversed.
* **Deep frame mode** — child frames are snapshotted with ``fN!eM`` refs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from playwright.async_api import Page

# ---------------------------------------------------------------------------
# In-page snapshot collector
# ---------------------------------------------------------------------------

SNAPSHOT_JS = r"""
() => {
  const MAX_NODES = (window.__navigatorMaxNodes || 400);
  const MAX_TEXT_BLOCKS = 70;
  const NAME_LIMIT = 80;
  const VALUE_LIMIT = 48;

  const nodes = [];
  const textBlocks = [];
  let truncated = false;

  const nextRef = () => {
    window.__navigatorRefCounter = (window.__navigatorRefCounter || 0) + 1;
    return 'e' + window.__navigatorRefCounter;
  };

  const INTERACTIVE = new Set([
    'link', 'button', 'textbox', 'searchbox', 'combobox', 'checkbox', 'radio',
    'switch', 'slider', 'spinbutton', 'option', 'tab', 'menuitem', 'menuitemcheckbox',
    'menuitemradio', 'treeitem', 'listbox', 'progressbar', 'scrollbar'
  ]);
  const STRUCTURAL = new Set([
    'banner', 'navigation', 'main', 'complementary', 'contentinfo', 'region',
    'form', 'search', 'dialog', 'alertdialog', 'article', 'table', 'grid',
    'list', 'menubar', 'menu', 'toolbar', 'tablist', 'group', 'figure'
  ]);
  const SKIP_TAGS = new Set([
    'script', 'style', 'meta', 'link', 'noscript', 'br', 'hr', 'template',
    'head', 'title', 'base', 'colgroup', 'col', 'option'
  ]);

  const INPUT_ROLE = {
    text: 'textbox', search: 'searchbox', email: 'textbox', password: 'textbox',
    tel: 'textbox', url: 'textbox', number: 'spinbutton', range: 'slider',
    checkbox: 'checkbox', radio: 'radio', submit: 'button', button: 'button',
    reset: 'button', image: 'button', date: 'textbox', 'datetime-local': 'textbox',
    month: 'textbox', time: 'textbox', week: 'textbox', color: 'textbox', file: 'button'
  };
  const TAG_ROLE = {
    a: 'link', button: 'button', select: 'combobox', textarea: 'textbox',
    nav: 'navigation', header: 'banner', main: 'main', aside: 'complementary',
    footer: 'contentinfo', form: 'form', dialog: 'dialog', table: 'table',
    ul: 'list', ol: 'list', menu: 'menu', menubar: 'menubar',
    toolbar: 'toolbar', tablist: 'tablist', figure: 'figure', img: 'image',
    svg: 'image', video: 'video', audio: 'audio', details: 'group',
    h1: 'heading', h2: 'heading', h3: 'heading', h4: 'heading',
    h5: 'heading', h6: 'heading'
  };

  function isVisible(el) {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' ||
        style.opacity === '0' || el.getAttribute('aria-hidden') === 'true') return false;
    if (!el.getClientRects().length) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 || r.height > 1;
  }

  function truncate(s, n) {
    s = (s || '').replace(/\s+/g, ' ').trim();
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  function roleFor(el) {
    const explicit = el.getAttribute('role');
    if (explicit) {
      const r = explicit.trim().split(/\s+/)[0].toLowerCase();
      if (r && r !== 'presentation' && r !== 'none') return r;
    }
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') {
      if (el.type === 'hidden') return null;
      return INPUT_ROLE[el.type] || 'textbox';
    }
    if (tag === 'h1') return 'heading';
    if (/^h[1-6]$/.test(tag)) return 'heading';
    if (tag === 'img') return (el.getAttribute('alt') || el.getAttribute('aria-label')) ? 'image' : null;
    if (tag === 'svg') return el.getAttribute('aria-label') ? 'image' : null;
    if (tag === 'a') return 'link';
    const mapped = TAG_ROLE[tag];
    if (mapped) return mapped;
    // clickable heuristics
    if (el.hasAttribute('onclick')) return 'button';
    const cls = typeof el.className === 'string' ? el.className.toLowerCase() : '';
    if (cls && (cls.includes('btn') || cls.includes('button')) &&
        window.getComputedStyle(el).cursor === 'pointer') return 'button';
    return null;
  }

  function labelFor(id) {
    if (!id) return null;
    const lab = document.querySelector(`label[for="${CSS.escape(id)}"]`);
    return lab ? lab.innerText : null;
  }

  function nameFor(el, role) {
    let n = el.getAttribute('aria-label');
    if (!n) {
      const labelledby = el.getAttribute('aria-labelledby');
      if (labelledby) {
        n = labelledby.split(/\s+/).map(
          id => (document.getElementById(id) || {}).innerText || ''
        ).join(' ').trim() || null;
      }
    }
    if (!n) n = labelFor(el.id);
    if (!n) n = el.getAttribute('placeholder');
    if (!n) n = el.getAttribute('title');
    if (!n && el.tagName.toLowerCase() === 'img') n = el.getAttribute('alt');
    if (!n && role === 'combobox') {
      const opt = el.selectedOptions && el.selectedOptions[0];
      if (opt) n = opt.label || opt.value;
    }
    if (!n) {
      n = el.innerText || el.textContent || '';
      n = n.split('\n').map(s => s.trim()).filter(Boolean)[0] || null;
    }
    if (!n && el.value && (el.tagName === 'INPUT' || el.tagName === 'BUTTON')) n = el.value;
    return n ? truncate(n, NAME_LIMIT) : null;
  }

  function statesFor(el, role) {
    const st = [];
    if (role === 'heading') {
      const m = el.tagName.toLowerCase().match(/^h([1-6])$/);
      if (m) st.push('level=' + m[1]);
    }
    if (el.checked === true || el.getAttribute('aria-checked') === 'true') st.push('checked');
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') st.push('disabled');
    if (el.getAttribute('aria-expanded') === 'true') st.push('expanded');
    if (el.getAttribute('aria-expanded') === 'false') st.push('collapsed');
    if (el.required || el.getAttribute('aria-required') === 'true') st.push('required');
    if (el.readOnly) st.push('readonly');
    if (el.selected || el.getAttribute('aria-selected') === 'true') st.push('selected');
    if (el.getAttribute('aria-invalid') === 'true') st.push('invalid');
    if (el.tagName === 'INPUT' && ['checkbox', 'radio'].includes(el.type) === false && el.value) {
      st.push('value=' + JSON.stringify(truncate(String(el.value), VALUE_LIMIT)));
    }
    return st;
  }

  function ensureRef(el) {
    let ref = el.getAttribute('data-navigator-ref');
    if (!ref) { ref = nextRef(); el.setAttribute('data-navigator-ref', ref); }
    return ref;
  }

  function emit(el, role, depth) {
    if (nodes.length >= MAX_NODES) { truncated = true; return; }
    const name = nameFor(el, role);
    const node = {
      ref: ensureRef(el),
      role: role,
      name: name || '',
      depth: depth,
      states: statesFor(el, role)
    };
    if (el.tagName && el.tagName.toLowerCase() === 'iframe') {
      node.framesrc = el.src || '';
    }
    nodes.push(node);
    return node;
  }

  // semantic depth = number of emitted ancestors
  function walk(el, depth) {
    if (nodes.length >= MAX_NODES) { truncated = true; return; }
    if (!(el instanceof Element)) return;
    const tag = el.tagName.toLowerCase();
    if (SKIP_TAGS.has(tag)) return;
    if (el.type === 'hidden') return;
    if (!isVisible(el)) {
      // hidden interactive elements still matter for a11y + scraping,
      // but skip them for normal perception to save tokens.
      return;
    }

    const role = roleFor(el);

    if (role && (INTERACTIVE.has(role) || role === 'heading' || role === 'image' ||
                 role === 'video' || role === 'audio')) {
      emit(el, role, depth);
      // still recurse to catch nested structure (menus inside buttons etc.)
      for (const child of el.children) walk(child, depth + 1);
      if (el.shadowRoot) {
        for (const child of el.shadowRoot.children) walk(child, depth + 1);
      }
      return;
    }

    if (role && STRUCTURAL.has(role)) {
      // emit structural container for tree organization; name only from
      // explicit labels — never from innerText (too noisy for the LLM)
      const node = emit(el, role, depth);
      if (node) node.name = el.getAttribute('aria-label') || '';
      for (const child of el.children) walk(child, depth + 1);
      if (el.shadowRoot) {
        for (const child of el.shadowRoot.children) walk(child, depth + 1);
      }
      return;
    }

    // plain container or unknown: recurse without emitting
    for (const child of el.children) walk(child, depth);
    if (el.shadowRoot) {
      for (const child of el.shadowRoot.children) walk(child, depth);
    }
  }

  function collectText() {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const t = node.textContent.trim();
        if (t.length < 3) return NodeFilter.FILTER_REJECT;
        let p = node.parentElement;
        while (p && p !== document.body) {
          if (p.getAttribute && p.getAttribute('data-navigator-ref')) return NodeFilter.FILTER_REJECT;
          p = p.parentElement;
        }
        if (p && p.getAttribute && p.getAttribute('data-navigator-ref')) return NodeFilter.FILTER_REJECT;
        const style = window.getComputedStyle(node.parentElement);
        if (style.display === 'none' || style.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    const seen = new Set();
    let n;
    while ((n = walker.nextNode())) {
      const t = truncate(n.textContent.trim(), 160);
      if (!t || seen.has(t) || textBlocks.length >= MAX_TEXT_BLOCKS) continue;
      seen.add(t);
      textBlocks.push(t);
    }
  }

  walk(document.body, 0);
  collectText();

  return {
    url: window.location.href,
    title: document.title,
    scrollY: Math.round(window.scrollY || 0),
    scrollHeight: Math.round(document.documentElement.scrollHeight || 0),
    viewport: { w: window.innerWidth, h: window.innerHeight },
    nodeCount: nodes.length,
    truncated,
    nodes,
    textBlocks,
    frames: Array.from(document.querySelectorAll('iframe')).slice(0, 8).map(f => ({
      name: f.name || f.title || f.getAttribute('aria-label') || 'unnamed',
      url: f.src || '(about:blank)'
    }))
  };
}
"""

# ---------------------------------------------------------------------------
# Python-side rendering
# ---------------------------------------------------------------------------


def _q(name: str) -> str:
    """Quote a name safely for the YAML-ish output."""
    name = name.replace('"', "'").replace("\n", " ").strip()
    return f'"{name}"' if name else ""


def render_snapshot(raw: dict[str, Any]) -> str:
    """Render the raw JS collector output into compact YAML-ish text."""
    lines: list[str] = []
    lines.append(f"# Page: {raw.get('title', '')[:100]}")
    lines.append(f"# URL: {raw.get('url', '')}")
    lines.append(
        f"# Scroll: {raw.get('scrollY', 0)}/{raw.get('scrollHeight', 0)}px "
        f"| Viewport: {raw.get('viewport', {}).get('w', 0)}x{raw.get('viewport', {}).get('h', 0)} "
        f"| Elements: {raw.get('nodeCount', 0)}"
    )
    if raw.get("truncated"):
        lines.append(
            "# NOTE: snapshot truncated — use browser_scroll + browser_snapshot "
            "or browser_find to see more elements"
        )

    for node in raw.get("nodes", []):
        depth = int(node.get("depth", 0))
        role = node.get("role", "element")
        parts = [role]
        if node.get("name"):
            parts.append(_q(node["name"]))
        for st in node.get("states", []):
            parts.append(f"[{st}]")
        parts.append(f"[ref={node.get('ref')}]")
        if node.get("framesrc"):
            parts.append(f"(frame: {node['framesrc'][:60]})")
        lines.append("  " * depth + "- " + " ".join(parts))

    if raw.get("textBlocks"):
        lines.append("# --- page text ---")
        for t in raw["textBlocks"]:
            lines.append(f'- text {_q(t)}')

    if raw.get("frames"):
        lines.append("# --- child frames (use browser_snapshot deep=true) ---")
        for i, f in enumerate(raw["frames"]):
            lines.append(f'# frame[{i}] "{f["name"]}" -> {f["url"][:100]}')

    return "\n".join(lines)


def snapshot_hash(raw: dict[str, Any]) -> str:
    """Content hash used for change detection / token-saving cache."""
    material = {
        "url": raw.get("url"),
        "title": raw.get("title"),
        "scrollY": raw.get("scrollY"),
        "nodes": [
            [n.get("ref"), n.get("role"), n.get("name"), n.get("states")]
            for n in raw.get("nodes", [])
        ],
    }
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


async def capture(page: Page, max_nodes: int = 400) -> dict[str, Any]:
    """Run the collector in the page's main frame."""
    try:
        await page.evaluate("n => { window.__navigatorMaxNodes = n; }", max_nodes)
    except Exception:
        pass
    raw = await page.evaluate(SNAPSHOT_JS)
    return raw


async def capture_deep(page: Page, max_nodes: int = 400) -> dict[str, Any]:
    """Capture the main frame plus child frames (merged, refs prefixed fN!)."""
    main = await capture(page, max_nodes)
    frames_out = []
    for idx, frame in enumerate(page.frames[1:], start=1):  # 0 is the main frame
        try:
            if not frame.url or frame.url == "about:blank":
                continue
            fraw = await frame.evaluate(SNAPSHOT_JS)
        except Exception:
            continue
        for node in fraw.get("nodes", []):
            node["ref"] = f"f{idx}!{node['ref']}"
        frames_out.append(
            {
                "index": idx,
                "url": fraw.get("url"),
                "title": fraw.get("title"),
                "nodes": fraw.get("nodes", []),
                "textBlocks": fraw.get("textBlocks", []),
            }
        )
    main["deepFrames"] = frames_out
    return main


def render_deep(raw: dict[str, Any]) -> str:
    """Render main snapshot + frame sections."""
    base = render_snapshot(raw)
    extra = []
    for f in raw.get("deepFrames", []):
        extra.append(f"\n# ===== FRAME[{f['index']}]: {f.get('title', '')[:60]} =====")
        extra.append(f"# URL: {f.get('url', '')}")
        for node in f.get("nodes", []):
            depth = int(node.get("depth", 0))
            parts = [node.get("role", "element")]
            if node.get("name"):
                parts.append(_q(node["name"]))
            for st in node.get("states", []):
                parts.append(f"[{st}]")
            parts.append(f"[ref={node.get('ref')}]")
            extra.append("  " * depth + "- " + " ".join(parts))
        for t in f.get("textBlocks", [])[:25]:
            extra.append(f'- text {_q(t)}')
    return base + ("\n".join(extra) if extra else "")


def parse_ref(ref: str) -> tuple[int | None, str]:
    """Split a possibly frame-prefixed ref into (frame_index, css_selector).

    ``e12`` -> (None, '[data-navigator-ref="e12"]')
    ``f2!e5`` -> (2, '[data-navigator-ref="e5"]')
    """
    ref = ref.strip()
    if "!" in ref:
        frame_part, elem_part = ref.split("!", 1)
        try:
            return int(frame_part[1:]), f'[data-navigator-ref="{elem_part}"]'
        except ValueError:
            pass
    return None, f'[data-navigator-ref="{ref}"]'
