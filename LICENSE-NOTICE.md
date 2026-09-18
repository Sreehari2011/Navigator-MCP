# Licensing Notice — Navigator MCP

## Source license (this repository)

Copyright (c) 2025 Navigator MCP.

**MIT License.** Personal project — use it, extend it, break it, have fun.
Attribution is appreciated, not enforced.

## Third-party components

| Component | License | Use |
|---|---|---|
| Playwright | Apache-2.0 | browser automation |
| FastMCP / mcp SDK | Apache-2.0 | MCP protocol server |
| httpx | BSD-3-Clause | HTTP client |
| uvicorn | BSD-3-Clause | HTTP transport |

## Acceptable use

The `reference/` directory contains parked security-testing code (OOB
callbacks, raw HTTP client, XSS probe) preserved for a future dedicated
Security MCP. It is **not installed with this package**. When revived, it is
intended for **authorized security testing only** — your own assets or
assets you have written permission to test. Operators are solely responsible
for compliance with the laws of their jurisdiction.
