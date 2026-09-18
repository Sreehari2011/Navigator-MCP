"""CLI entry point.

  navigator-mcp                        → stdio (Claude Desktop, Cursor, VS Code)
  navigator-mcp --transport http       → Streamable HTTP on NAVIGATOR_HTTP_HOST:PORT
"""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="navigator-mcp",
        description="Navigator MCP — high-performance browser automation "
        "for LLMs (perception, stealth, captchas, traffic)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport: stdio (local clients) or http (server deployment)",
    )
    parser.add_argument("--host", default=None, help="HTTP bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="HTTP port (default 8765)")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("--verbose", action="store_true", help="Debug logging to stderr")
    args = parser.parse_args(argv)

    if args.version:
        from . import __version__

        print(f"navigator-mcp {__version__}")
        return 0

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if args.transport == "stdio":
        from .server import build_server

        build_server().run()
        return 0

    # ---- HTTP ---------------------------------------------------------------
    import uvicorn

    from .config import get_settings
    from .server import build_http_app

    settings = get_settings()
    app = build_http_app()
    uvicorn.run(
        app,
        host=args.host or settings.http_host,
        port=args.port or settings.http_port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
