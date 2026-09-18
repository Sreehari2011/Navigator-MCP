"""HTTP transport smoke test: API-key gate, /health, MCP initialize handshake.

Boots the real server as a subprocess on a scratch port, then verifies:

1. ``GET /health`` reports ``service=navigator-mcp``
2. ``POST /mcp`` without a key is rejected with 401
3. The MCP ``initialize`` handshake with the key returns serverInfo
   naming "Navigator MCP"

Run directly (``python scripts/http_smoke.py``) or via ``scripts/run_checks.sh``.
Override the port with ``SMOKE_PORT`` if the default is taken.
"""

import asyncio
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

PORT = int(os.environ.get("SMOKE_PORT", "8899"))
KEY = "sk-smoke-test"
ROOT = Path(__file__).resolve().parent.parent


async def wait_for_health(client: httpx.AsyncClient) -> httpx.Response:
    for _ in range(40):
        try:
            return await client.get(f"http://127.0.0.1:{PORT}/health")
        except httpx.HTTPError:
            await asyncio.sleep(0.5)
    raise RuntimeError("server did not come up within 20 seconds")


async def main() -> None:
    env = dict(os.environ)
    env.update(
        {
            "NAVIGATOR_API_KEYS": KEY,
            "NAVIGATOR_HTTP_HOST": "127.0.0.1",
            "NAVIGATOR_HTTP_PORT": str(PORT),
            "NAVIGATOR_WORKSPACE": tempfile.mkdtemp(prefix="nav-smoke-"),
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "navigator_mcp", "--transport", "http"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        async with httpx.AsyncClient() as c:
            # 1. health
            r = await wait_for_health(c)
            assert r.status_code == 200, r.status_code
            body = r.json()
            assert body["service"] == "navigator-mcp", body
            print(f"[1] /health: 200 {body}")

            # 2. no key -> 401
            r = await c.post(f"http://127.0.0.1:{PORT}/mcp", json={"ping": 1})
            assert r.status_code == 401, r.status_code
            print("[2] /mcp without key: 401 (gate works)")

            # 3. initialize handshake with the key
            r = await c.post(
                f"http://127.0.0.1:{PORT}/mcp",
                headers={
                    "x-api-key": KEY,
                    "accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "smoke", "version": "0"},
                    },
                },
            )
            assert r.status_code == 200, r.status_code
            assert '"serverInfo"' in r.text and "Navigator MCP" in r.text
            print("[3] MCP initialize handshake with key: serverInfo = Navigator MCP")

        print("\nHTTP SMOKE PASSED")
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
