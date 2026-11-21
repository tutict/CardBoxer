"""把「玩家 vs 对手怪剪影一眼可分」变成可复算的数字。

设计目标（先验，不是事后凑阈值）：
  * 对手怪不透明区平均明度应 <= 玩家的 0.75（深浅对立）
  * 对手怪宽高比应 >= 玩家的 1.15（体量对立）
  * 对手怪肩部最大横向跨度应 >= 玩家的 1.15（宽肩对立）

只量正面全身图，两者都是 render_character.py 同相机、归一化到 1.72m。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
PLAYER = BAKE / "3D模型探针V4b" / "v4b-front.png"
FOE = HERE / "foe-front.png"


def measure(p: Path) -> dict:
    with Image.open(p) as s:
        im = s.convert("RGBA")
    w, h = im.size
    rgb = im.convert("RGB")
    a = im.getchannel("A")
    mask = a.point(lambda v: 255 if v > 8 else 0)
    bb = mask.getbbox()
    assert bb, f"empty alpha: {p.name}"
    x0, y0, x1, y1 = bb
    bw, bh = x1 - x0, y1 - y0

    px = rgb.load()
    ma = mask.load()
    lum, n = 0.0, 0
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            if ma[x, y]:
                r, g, b = px[x, y]
                lum += 0.2126 * r + 0.7152 * g + 0.0722 * b
                n += 1
    mean_lum = lum / max(n, 1) / 255.0

    # 肩带：身高 20%~40% 区间，逐行取 alpha>8 的最大横向跨度
    spans = []
    for y in range(y0 + round(bh * 0.20), y0 + round(bh * 0.40)):
        xs = [x for x in range(x0, x1) if ma[x, y]]
        if xs:
            spans.append(max(xs) - min(xs) + 1)
    shoulder = max(spans) if spans else 0

    return {
        "file": p.name,
        "canvas": [w, h],
        "alpha_bbox": [x0, y0, x1, y1],
        "body_wh": [bw, bh],
        "aspect_wh": round(bw / bh, 4),
        "mean_luminance": round(mean_lum, 4),
        "shoulder_max_span_px": shoulder,
        "opaque_sample_px": n,
    }


player = measure(PLAYER)
foe = measure(FOE)
ratios = {
    "luminance_foe_over_player": round(foe["mean_luminance"] / player["mean_luminance"], 4),
    "aspect_foe_over_player": round(foe["aspect_wh"] / player["aspect_wh"], 4),
    "shoulder_foe_over_player": round(
        foe["shoulder_max_span_px"] / player["shoulder_max_span_px"], 4),
}
goals = {
    "luminance_dark_enough": ratios["luminance_foe_over_player"] <= 0.75,
    "aspect_bulky_enough": ratios["aspect_foe_over_player"] >= 1.15,
    "shoulder_broad_enough": ratios["shoulder_foe_over_player"] >= 1.15,
}
out = {
    "note": "同相机 / 同归一化身高 1.72m 下的正面剪影与明度实测",
    "design_goals": {"max_luminance_ratio": 0.75, "min_aspect_ratio": 1.15,
                     "min_shoulder_ratio": 1.15},
    "player_v4b": player,
    "foe_v1": foe,
    "ratios": ratios,
    "goals": goals,
    "verdict": "SILHOUETTE_CONTRAST_OK" if all(goals.values()) else "SILHOUETTE_CONTRAST_SHORT",
}
(HERE / "silhouette_stats.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
