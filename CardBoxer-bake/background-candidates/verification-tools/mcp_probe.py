"""Temporary MCP client used for the 2026-11-05 usefulness check.

Reads the Studio connection token from FANTASY_STUDIO_MCP_TOKEN, never prints it.
Usage:
    python mcp_probe.py schemas
    python mcp_probe.py call <tool_name> <arguments-json-file>
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

BASE = "http://127.0.0.1:7860"
TARGETS = (
    "probe_comfyui_capabilities",
    "prepare_visual_reference_workflows",
    "run_visual_reference_workflow",
    "prepare_comfyui_plan",
)


async def main() -> int:
    mode = sys.argv[1]
    token = os.environ.get("FANTASY_STUDIO_MCP_TOKEN", "")
    if not token:
        print("missing token")
        return 2
    async with (
        httpx2.AsyncClient(
            headers={"Authorization": "Bearer " + token}, timeout=120, trust_env=False
        ) as client,
        streamable_http_client(BASE + "/mcp", http_client=client) as streams,
        ClientSession(*streams, read_timeout_seconds=120) as session,
    ):
        await session.initialize()
        tools = (await session.list_tools()).tools
        by_name = {tool.name: tool for tool in tools}
        if mode == "schemas":
            names = sys.argv[2:] or TARGETS
            for name in names:
                tool = by_name.get(name)
                if not tool:
                    print(f"--- {name}: NOT EXPOSED")
                    continue
                print(f"--- {name}")
                print(json.dumps(tool.input_schema, ensure_ascii=False, indent=2)[:3500])
            return 0
        if mode == "call":
            name = sys.argv[2]
            args = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
            result = await session.call_tool(name, args)
            print("is_error:", result.is_error)
            for block in result.content:
                text = getattr(block, "text", "")
                if text:
                    print("text:", text[:2000])
            if result.structured_content:
                print("structured_content:", json.dumps(result.structured_content, ensure_ascii=False)[:4000])
            return 0
        print("unknown mode")
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
