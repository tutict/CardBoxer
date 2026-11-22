"""Check whether the MCP allowlist template runs unchanged on the new SDXL model.

Submits templates/comfyui/ui-reference.json with ONLY the placeholders filled
in -- width/height, steps, cfg, sampler and scheduler stay exactly as shipped.
This is the workflow the Studio MCP would build for a visual-reference job.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import gen_bg_sdxl as g

TEMPLATE = Path(r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\templates\comfyui\ui-reference.json")
OUT = Path(r"D:\Projects\CardBoxer\CardBoxer-bake\background-candidates\mcp_template_sdxl.png")


def main() -> int:
    values = {
        "prompt": g.PROMPT,
        "negative_prompt": g.NEGATIVE,
        "seed": 424242,
        "output_path": "unused",
        "job_id": "mcp-template-sdxl",
        "gameplay_constraint": "2D side-view fighting game arena backdrop",
        "checkpoint_name": "sd_xl_base_1.0.safetensors",
        "filename_prefix": "CardBoxer/mcp_template_sdxl",
    }
    wf = g.inject(json.loads(TEMPLATE.read_text(encoding="utf-8")), values)
    print("template params: latent=%sx%s steps=%s cfg=%s sampler=%s/%s" % (
        wf["4"]["inputs"]["width"], wf["4"]["inputs"]["height"],
        wf["5"]["inputs"]["steps"], wf["5"]["inputs"]["cfg"],
        wf["5"]["inputs"]["sampler_name"], wf["5"]["inputs"]["scheduler"],
    ), flush=True)
    response = g.request("/prompt", {"prompt": wf, "client_id": "mcp-template-check"})
    prompt_id = response.get("prompt_id")
    print("queued:", prompt_id, flush=True)
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        record = g.request(f"/history/{prompt_id}").get(prompt_id, {})
        status = record.get("status", {})
        if status.get("status_str") == "error":
            messages = [m[1] for m in status.get("messages", []) if m[0] == "execution_error"]
            print("FAILED:", json.dumps(messages, ensure_ascii=False)[:900], flush=True)
            return 1
        images = [im for out in record.get("outputs", {}).values() for im in out.get("images", [])]
        if images:
            image = images[0]
            query = urllib.parse.urlencode({
                "filename": image["filename"],
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            })
            with g.OPENER.open(urllib.request.Request(g.BASE + "/view?" + query), timeout=120) as resp:
                OUT.write_bytes(resp.read())
            print(f"OK: saved {OUT} ({OUT.stat().st_size} bytes)", flush=True)
            return 0
        time.sleep(2.0)
    print("TIMEOUT", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
