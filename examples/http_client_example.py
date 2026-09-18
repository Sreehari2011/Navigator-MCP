"""Connect to a remote Navigator MCP HTTP deployment with an API key.

Run the server first:
    NAVIGATOR_API_KEYS=sk-my-key navigator-mcp --transport http --host 0.0.0.0 --port 8765
"""

import asyncio
import os

from fastmcp import Client

SERVER_URL = os.environ.get("NAVIGATOR_URL", "http://127.0.0.1:8765/mcp")
API_KEY = os.environ.get("NAVIGATOR_API_KEY", "sk-my-key")


async def main() -> None:
    headers = {"X-API-Key": API_KEY}
    async with Client(SERVER_URL, headers=headers) as client:
        # health is unauthenticated (plain httpx would also work)
        tools = await client.list_tools()
        print(f"connected: {len(tools)} tools available")

        result = await client.call_tool(
            "browser_navigate", {"url": "https://example.com"}
        )
        print(result.content[0].text[:600])


if __name__ == "__main__":
    asyncio.run(main())
