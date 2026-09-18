"""JavaScript execution tools."""

from __future__ import annotations

import json

from fastmcp.exceptions import ToolError

from ._base import page_for


def _safe_repr(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


async def browser_evaluate(
    expression: str,
    arg: str | None = None,
    session: str = "default",
    tab: int | None = None,
) -> str:
    """Evaluate JavaScript in the page and return the result.

    Prefer a function expression: "() => document.title" or
    "(x) => fetch(x).then(r => r.status)" with arg passed as parameter.
    Everything the page can do is allowed — this is raw power, use responsibly.
    """
    runtime, _, ps = await page_for(session, tab)
    try:
        if arg is not None:
            result = await ps.page.evaluate(expression, arg)
        else:
            result = await ps.page.evaluate(expression)
    except Exception as exc:
        raise ToolError(f"JS evaluation failed: {exc}") from exc
    runtime.meter.record("browser_evaluate")
    text = _safe_repr(result)
    if len(text) > 20000:
        text = text[:20000] + f"…[truncated from {len(text)} chars]"
    return f"JS result: {text}"
