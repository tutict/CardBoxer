"""Walk the full Studio MCP chain for one ComfyUI background-image request.

Evidence only: every step prints status/summary; the token is never printed.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

BASE = "http://127.0.0.1:7860"
IDEA = (
    "A 2D side-view card-battling boxing game. Replace the arena backdrop with a "
    "night-time rooftop boxing ring: deep indigo sky, distant city silhouettes, "
    "warm amber spotlights on the left, cool cyan on the right, empty centre so "
    "the two fighters stay readable, no characters, no text, wide 16:9 composition."
)


def brief(result) -> dict:
    data = result.structured_content or {}
    if not data:
        for block in result.content:
            text = getattr(block, "text", "")
            if text:
                try:
                    data = json.loads(text)
                except ValueError:
                    data = {"text": text}
                break
    return data


async def call(session, name: str, args: dict, label: str):
    result = await session.call_tool(name, args)
    data = brief(result)
    print(f"[{label}] is_error={result.is_error} status={data.get('status')} "
          f"summary={str(data.get('summary', ''))[:220]}")
    keys = {k: data[k] for k in ("project_id", "plan_version", "grant_id", "intent_id", "kind")
            if k in data}
    if keys:
        print(f"[{label}] keys={json.dumps(keys, ensure_ascii=False)}")
    return data, result.is_error


async def main() -> int:
    token = os.environ.get("FANTASY_STUDIO_MCP_TOKEN", "")
    if not token:
        print("missing token")
        return 2
    async with (
        httpx2.AsyncClient(
            headers={"Authorization": "Bearer " + token}, timeout=600, trust_env=False
        ) as client,
        streamable_http_client(BASE + "/mcp", http_client=client) as streams,
        ClientSession(*streams, read_timeout_seconds=600) as session,
    ):
        await session.initialize()

        data, error = await call(session, "create_project", {"name": "牌拳-背景图-实用性检测"}, "1 create_project")
        if error:
            return 1
        project_id = data.get("project_id") or (data.get("project") or {}).get("project_id")
        if not project_id:
            print("[1] full payload:", json.dumps(data, ensure_ascii=False)[:1200])
            return 1

        data, error = await call(
            session,
            "prepare_comfyui_plan",
            {"prompt": IDEA, "project_id": project_id, "source_locale": "en"},
            "2 prepare_comfyui_plan",
        )
        plan_version = data.get("plan_version")
        if plan_version is None:
            print("[2] full payload:", json.dumps(data, ensure_ascii=False)[:1200])
            return 1

        await call(
            session,
            "get_project_snapshot",
            {"project_id": project_id, "plan_version": plan_version},
            "3 get_project_snapshot",
        )

        data, error = await call(
            session,
            "run_visual_reference_workflow",
            {
                "project_id": project_id,
                "plan_version": plan_version,
                "wait_for_completion": True,
                "timeout_seconds": 300,
                "poll_interval_seconds": 2.0,
            },
            "4 run_visual_reference_workflow",
        )
        print("[4] full payload:", json.dumps(data, ensure_ascii=False)[:2500])
        return 0


if __name__ == "__main__":
    sys_exit = asyncio.run(main())
    raise SystemExit(sys_exit)
