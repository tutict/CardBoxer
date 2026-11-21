"""诊断 baseline vs off 的像素差异量级：是量化抖动还是内容不同。

用法：python diag_ab.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
OUT = HERE / "data" / "diag_ab.json"
NAME = "节奏帧-t048-命中HIT.png"
REGIONS = {
    "top_bg": (0, 0, 1280, 180),
    "mid": (0, 180, 1280, 520),
    "bottom_hud": (0, 520, 1280, 720),
    "player": (290, 270, 580, 535),
}


def stat(a: Image.Image, b: Image.Image) -> dict:
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    px = list(d.get_flattened_data())
    n = len(px)
    total = sum(sum(p) for p in px)
    buckets = {"eq0": 0, "1to2": 0, "3to6": 0, "7to16": 0, "gt16": 0}
    for p in px:
        m = max(p)
        if m == 0:
            buckets["eq0"] += 1
        elif m <= 2:
            buckets["1to2"] += 1
        elif m <= 6:
            buckets["3to6"] += 1
        elif m <= 16:
            buckets["7to16"] += 1
        else:
            buckets["gt16"] += 1
    return {
        "pixels": n,
        "mae": round(total / (n * 3), 5),
        "max_channel": max(max(p) for p in px),
        "buckets": buckets,
        "changed_gt6": buckets["7to16"] + buckets["gt16"],
        "bbox": d.getbbox(),
    }


def main() -> int:
    pairs = {
        "baseline_vs_off": (SHOTS / "baseline" / NAME, SHOTS / "off" / NAME),
        "on_vs_off": (SHOTS / "on" / NAME, SHOTS / "off" / NAME),
        "baseline_vs_on": (SHOTS / "baseline" / NAME, SHOTS / "on" / NAME),
    }
    out = {}
    for k, (pa, pb) in pairs.items():
        if not (pa.is_file() and pb.is_file()):
            out[k] = {"error": "missing"}
            continue
        a, b = Image.open(pa), Image.open(pb)
        out[k] = {"whole": stat(a, b), "regions": {
            name: stat(a.crop(box), b.crop(box))
            for name, box in REGIONS.items()}}
        d = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
        # 8 倍放大，肉眼看差异分布
        d.point(lambda v: min(255, v * 8)).save(
            HERE / "shots" / ("diag-diff-%s.png" % k))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in out.items():
        if "error" in v:
            print(k, v["error"])
            continue
        w = v["whole"]
        print(f"{k:18s} mae={w['mae']:<9} max={w['max_channel']:<4} "
              f"gt6={w['changed_gt6']:<8} buckets={w['buckets']}")
        for r, s in v["regions"].items():
            print(f"    {r:12s} mae={s['mae']:<9} gt6={s['changed_gt6']:<8} "
                  f"max={s['max_channel']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
