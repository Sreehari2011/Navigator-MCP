#!/usr/bin/env bash
# Navigator MCP — full verification suite.
#
# Usage:
#   ./scripts/run_checks.sh            # lint + unit tests + browser E2E + HTTP smoke
#   ./scripts/run_checks.sh --fast     # lint + unit tests only (no browser, no server)
#
# Prerequisites:
#   pip install -e ".[dev]"
#   playwright install chromium        # only needed for the E2E part
#
# Override the python interpreter with NAVIGATOR_PYTHON (defaults to python3).

set -euo pipefail
cd "$(dirname "$0")/.."

PY="${NAVIGATOR_PYTHON:-python3}"
FAST=0
[ "${1:-}" = "--fast" ] && FAST=1

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
ok()  { printf '\033[1;32m OK  %s\033[0m\n' "$1"; }

say "Version"
$PY -c "import navigator_mcp as n; print('navigator-mcp', n.__version__)"

say "Lint (ruff)"
if command -v ruff >/dev/null 2>&1; then
    ruff check .
    ok "ruff clean"
else
    echo "  skipped (ruff not on PATH)"
fi

say "Unit + integration tests (pytest)"
$PY -m pytest -q
ok "pytest green"

if [ "$FAST" -eq 1 ]; then
    say "Fast mode — skipping browser E2E and HTTP smoke"
    printf '\n\033[1;32mFAST CHECKS PASSED\033[0m\n'
    exit 0
fi

say "E2E browser loop (real Chromium)"
$PY scripts/e2e_browser.py
ok "E2E green"

say "HTTP transport smoke (API-key gate + initialize handshake)"
$PY scripts/http_smoke.py
ok "HTTP smoke green"

say "Tool registry"
$PY - <<'EOF'
import asyncio

from fastmcp import Client

from navigator_mcp.server import build_server


async def main() -> None:
    async with Client(build_server()) as c:
        tools = await c.list_tools()
    names = sorted(t.name for t in tools)
    assert len(names) == 51, f"expected 51 tools, got {len(names)}"
    assert not any(n.startswith(("security_", "argus_")) for n in names), names
    assert "navigator_status" in names
    print(f"{len(names)} tools: 49 browser_* + navigator_status + usage_report")


asyncio.run(main())
EOF
ok "registry verified"

printf '\n\033[1;32mALL CHECKS PASSED — Navigator MCP is healthy.\033[0m\n'
