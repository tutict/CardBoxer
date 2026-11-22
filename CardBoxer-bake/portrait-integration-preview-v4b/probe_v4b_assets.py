"""量 V4b 四视角渲染图的 alpha 包围盒，给出合成脚本要用的 SUBJECT / 脸部裁框。

不能照抄 V3 的 SUBJECT：不同模型、不同配饰，人物在 768² 画布里的占位不同。
同时读一遍 V3 作对照，确认两者画布口径一致（同为 render_character.py 的 7-shot 相机）。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
V3 = BAKE / "3d-model-probe-v3"
V4B = BAKE / "3d-model-probe-v4b"
SHOTS = ["front", "angle25", "angle55", "back35"]


def stat(p: Path) -> dict:
    with Image.open(p) as s:
        im = s.convert("RGBA")
    a = im.getchannel("A")
    bb = a.getbbox()
    # alpha>8 的严格包围盒，与 V3 probe_assets.py 同口径
    mask = a.point(lambda v: 255 if v > 8 else 0)
    strict = mask.getbbox()
    opaque = sum(1 for v in a.get_flattened_data() if v > 8)
    return {
        "file": p.name,
        "size": list(im.size),
        "alpha_bbox": list(bb) if bb else None,
        "strict_bbox": list(strict) if strict else None,
        "opaque_px": opaque,
        "bytes": p.stat().st_size,
    }


def alpha_profile(p: Path) -> dict:
    """脸特写的 alpha 分布：判断是透明背景还是实黑底，决定头像母图怎么抠。"""
    with Image.open(p) as s:
        im = s.convert("RGBA")
    a = im.getchannel("A")
    hist = a.histogram()
    total = im.width * im.height
    corners = [im.getpixel(pt) for pt in ((0, 0), (im.width - 1, 0),
                                          (0, im.height - 1), (im.width - 1, im.height - 1))]
    return {
        "file": p.name, "size": list(im.size),
        "alpha_0_pct": round(hist[0] / total, 4),
        "alpha_255_pct": round(hist[255] / total, 4),
        "alpha_bbox": list(a.getbbox()) if a.getbbox() else None,
        "corners_rgba": corners,
    }


out = {"v4b": [], "v3": [], "face": [],
       "camera_note": "render_character.py 7-shot, 768x768 / face 1024x1024"}
for k in SHOTS:
    p = V4B / f"v4b-{k}.png"
    out["v4b"].append(stat(p) if p.exists() else {"shot": k, "error": "MISSING"})
    q = V3 / f"zzz-{k}.png"
    out["v3"].append(stat(q) if q.exists() else {"shot": k, "error": "MISSING"})
for k in ("face-front", "face-25"):
    p = V4B / f"v4b-{k}.png"
    out["face"].append(alpha_profile(p) if p.exists() else {"shot": k, "error": "MISSING"})

# 脸部裁框：按 front 的 strict bbox 上部推导，不靠目测
f = next((x for x in out["v4b"] if x.get("file") == "v4b-front.png"), None)
if f and f.get("strict_bbox"):
    x0, y0, x1, y1 = f["strict_bbox"]
    cx = (x0 + x1) // 2
    head_h = round((y1 - y0) * 0.30)  # 头约占身高 30%
    half = round((x1 - x0) * 0.42)
    out["suggested_face_crop"] = [
        max(0, cx - half), max(0, y0 - 4),
        min(f["size"][0], cx + half), min(f["size"][1], y0 + head_h),
    ]
    out["suggested_subject"] = {
        k: (next(x for x in out["v4b"] if x.get("file") == f"v4b-{k}.png")["strict_bbox"])
        for k in SHOTS
    }

(HERE / "probe_v4b_assets.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
for group in ("v4b", "v3", "face"):
    for s in out[group]:
        print(group.upper(), json.dumps(s, ensure_ascii=False))
print("SUGGEST_FACE", json.dumps(out.get("suggested_face_crop")))
print("SUGGEST_SUBJECT", json.dumps(out.get("suggested_subject"), ensure_ascii=False))
print("PROBE_V4B_OK")
