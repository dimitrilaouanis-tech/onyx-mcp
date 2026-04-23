"""Atomic stdio MCP test — spawn server.py, speak MCP, assert tool answers."""
import asyncio
import base64
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    here = Path(__file__).parent
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(here / "server.py")],
        cwd=str(here),
    )

    test_img = Path(r"C:\Users\intelligence\assemble_debug\xc_target_crop.png")
    img_b64 = base64.b64encode(test_img.read_bytes()).decode()

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"[1] tools listed: {[t.name for t in tools.tools]}")

            result = await session.call_tool(
                "onyx_solve_captcha",
                arguments={"image_b64": img_b64},
            )
            print(f"[2] tool result: {result.content[0].text}")
            payload = json.loads(result.content[0].text)
            assert "answer" in payload, "missing answer"
            assert payload["source"] == "onyx.ddddocr"
            print(f"[3] answer={payload['answer']!r} in {payload['elapsed_ms']}ms")
            print("\n*** MCP PIPE WORKS END-TO-END ***")


if __name__ == "__main__":
    asyncio.run(main())
