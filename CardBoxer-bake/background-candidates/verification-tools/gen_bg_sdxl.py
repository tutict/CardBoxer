"""Generate CardBoxer arena backdrop candidates with SDXL 1.0 Base.

Reuses the allowlisted API-format workflow template; only the checkpoint and
sampler parameters change. The template must stay a CheckpointLoaderSimple
graph so the Studio MCP capability probe keeps working.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8188"
TEMPLATE = Path(r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\templates\comfyui\ui-reference.json")
OUT = Path(r"D:\Projects\CardBoxer\CardBoxer-bake\background-candidates")
CHECKPOINT = "sd_xl_base_1.0.safetensors"

PROMPT = (
    "stylized 2D fighting game stage background, side-view horizontal wide composition, "
    "night-time boxing arena seen straight from the side, very dark low-key lighting, "
    "deep indigo and violet night, desaturated, dim, "
    "three horizontal boxing ring ropes in shadow, dark corner posts, "
    "faint warm amber spotlight beam from upper left, faint cool cyan spotlight beam from upper right, "
    "dark blurred audience silhouettes, distant dark city skyline silhouette behind, "
    "matte near-black floor with subtle perspective lines, "
    "horizon line low in the frame, wide empty dark centre kept clear for two fighters, "
    "flat cel-shaded vector shapes, painterly game concept art, minimal detail, "
    "clean silhouettes, no bright backdrop, no curtain, no characters, no text"
)
NEGATIVE = (
    "people, character, fighter, face, hands, body, text, letters, watermark, logo, signature, "
    "UI, HUD, cards, landscape, mountains, desert, canyon, outdoor, nature, trees, rocks, water, "
    "clouds, planet, moon, sun, stars, birds, animals, creatures, monsters, "
    "bright, saturated, orange wall, glowing wall, curtain, stage backdrop, neon, "
    "photorealistic, photo, noise, grain, busy, clutter, high contrast foreground, "
    "lens flare, multiple panels, collage, deformed, jpeg artifacts"
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
    try:
        with OPENER.open(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} on {path}: {exc.read().decode('utf-8', 'replace')[:1600]}")
        raise


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
        "job_id": f"arena-sdxl-{index}",
        "gameplay_constraint": "2D side-view fighting game arena backdrop",
        "checkpoint_name": CHECKPOINT,
        "filename_prefix": f"CardBoxer/arena_sdxl_dark_{index:02d}",
    }
    wf = inject(template, values)
    # 保持仓库 allowlist 模板的原样 VAEDecode：下载缓存释放后 RAM 回到 10GB，
    # 全图解码不再 bad allocation；分块 VAE 在这台机器上反而慢到分钟级。
    wf["4"]["inputs"]["width"] = 896
    wf["4"]["inputs"]["height"] = 504
    wf["5"]["inputs"]["steps"] = 24
    wf["5"]["inputs"]["cfg"] = 6.5
    wf["5"]["inputs"]["sampler_name"] = "dpmpp_2m"
    wf["5"]["inputs"]["scheduler"] = "karras"
    return wf


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = [20261105, 733193, 481516]
    for index, seed in enumerate(seeds, start=1):
        response = request("/prompt", {"prompt": workflow(seed, index), "client_id": "cardboxer-sdxl"})
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            print(f"[{index}] no prompt_id: {response}")
            return 1
        print(f"[{index}] queued prompt_id={prompt_id} seed={seed}", flush=True)
        deadline = time.monotonic() + 600
        images = []
        while time.monotonic() < deadline:
            history = request(f"/history/{prompt_id}")
            record = history.get(prompt_id, {})
            status = record.get("status", {})
            if status.get("status_str") == "error":
                print(f"[{index}] ComfyUI error: {json.dumps(status, ensure_ascii=False)[:800]}")
                return 1
            for output in record.get("outputs", {}).values():
                images.extend(output.get("images", []))
            if images:
                break
            time.sleep(2.0)
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
        with OPENER.open(urllib.request.Request(BASE + "/view?" + query), timeout=120) as resp:
            blob = resp.read()
        target = OUT / f"arena_bg_sdxl_dark_{index:02d}.png"
        target.write_bytes(blob)
        print(f"[{index}] saved {target} ({len(blob)} bytes, source={image['filename']})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
