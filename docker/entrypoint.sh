#!/usr/bin/env bash
# Navigator MCP container entrypoint.
#   default (no args)          -> stdio server for Claude Desktop etc.
#   --transport http ...       -> HTTP server with API-key auth
#   --headful                  -> start Xvfb + VNC + fluxbox, run headless=false
set -e

MODE=""
for arg in "$@"; do
    case "$arg" in
        --headful) MODE="headful" ;;
    esac
done

if [ "$MODE" = "headful" ]; then
    echo "[navigator] starting virtual display (DISPLAY=:99) + VNC on :5901" >&2
    Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
    export DISPLAY=:99
    fluxbox >/dev/null 2>&1 &
    x11vnc -display :99 -forever -shared -nopw >/dev/null 2>&1 &
    export NAVIGATOR_HEADLESS=false
    # drop the --headful flag from the arg list
    set -- $(printf "%s " "$@" | sed 's/--headful//')
fi

if [ "$#" -eq 0 ]; then
    exec tini -- navigator-mcp
fi

exec tini -- navigator-mcp "$@"
