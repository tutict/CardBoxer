"""Generate CardBoxer arena backdrop candidates with a local ComfyUI instance.

Uses the allowlisted API-format template with custom prompts; bypasses the
Studio project/authorization chain on purpose (see the usefulness report).
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8188"
TEMPLATE = Path(r"C:\Users\tutic\AppData\Local\Temp\fa-mcp-check\templates\comfyui\ui-reference.json")
OUT = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\背景图候选")
CHECKPOINT = "v1-5-pruned-emaonly.safetensors"

PROMPT = (
    "2D fighting game stage background, side view boxing ring at night, "
    "dark empty arena, three horizontal boxing ring ropes, "
    "two bright spotlights shining down from above, dark audience silhouettes, "
    "deep indigo blue and purple, simple flat vector shapes, cel shaded, "
    "wide horizontal game art, empty center stage, no fighters"
)
NEGATIVE = (
    "landscape, mountains, desert, canyon, outdoor, nature, trees, rocks, water, "
    "sky, clouds, planet, moon, sun, stars, birds, animals, creatures, monsters, "
    "people, character, fighter, face, hands, body, text, letters, watermark, logo, "
    "photorealistic, photo, noise, grain, busy, clutter, detailed, bright, colorful, "
    "multiple panels, collage, deformed, jpeg artifacts"
)

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with OPENER.open(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def inject(value, values):
    if isinstance(value, dict):
        return {k: inject(v, values) for k, v in value.items()}
    if isinstance(value, list):
        return [inject(v, values) for v in value]
    if isinstance(value, str):
        for key, replacement in values.items():
            token = "{{ " + key + " }}"
            if value == token:
                return replacement
            value = value.replace(token, str(replacement))
    return value


def workflow(seed: int, index: int) -> dict:
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    values = {
        "prompt": PROMPT,
        "negative_prompt": NEGATIVE,
        "seed": seed,
        "output_path": "unused",
        "job_id": f"arena-bg-{index}",
        "gameplay_constraint": "2D side-view fighting game arena backdrop",
        "checkpoint_name": CHECKPOINT,
        "filename_prefix": f"CardBoxer/arena_v2_{index:02d}",
    }
    wf = inject(template, values)
    wf["4"]["inputs"]["width"] = 768
    wf["4"]["inputs"]["height"] = 432
    wf["5"]["inputs"]["steps"] = 26
    wf["5"]["inputs"]["cfg"] = 7.5
    return wf


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = [918273, 556677, 314159]
    for index, seed in enumerate(seeds, start=1):
        response = request("/prompt", {"prompt": workflow(seed, index), "client_id": "cardboxer-bg"})
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            print(f"[{index}] no prompt_id: {response}")
            return 1
        print(f"[{index}] queued prompt_id={prompt_id} seed={seed}", flush=True)
        deadline = time.monotonic() + 180
        images = []
        while time.monotonic() < deadline:
            history = request(f"/history/{prompt_id}")
            record = history.get(prompt_id, {})
            for output in record.get("outputs", {}).values():
                images.extend(output.get("images", []))
            if images:
                break
            time.sleep(1.5)
        if not images:
            print(f"[{index}] TIMEOUT")
            return 1
        image = images[0]
        query = urllib.parse.urlencode(
            {
                "filename": image["filename"],
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            }
        )
        req = urllib.request.Request(BASE + "/view?" + query)
        with OPENER.open(req, timeout=60) as resp:
            blob = resp.read()
        target = OUT / f"arena_bg_v2_{index:02d}.png"
        target.write_bytes(blob)
        print(f"[{index}] saved {target} ({len(blob)} bytes, source={image['filename']})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
