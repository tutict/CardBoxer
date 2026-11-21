"""Diagnose why the CONSTANT 3-band ramp produced almost no visible bands.

Hypothesis: world strength 0.75 + SUN 2.6 over-exposes ShaderToRGB, so nearly
every pixel lands in the top band. Measure the luminance histogram of the
opaque pixels instead of guessing a new light value.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
target = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "zzz-front.png"
im = Image.open(target).convert("RGBA")
w, h = im.size
px = list(im.getdata()) if not hasattr(im, "get_flattened_data") else list(im.get_flattened_data())

opaque = [(r, g, b) for r, g, b, a in px if a > 128]


def lum(c):
    r, g, b = c
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


vals = [lum(c) for c in opaque]
buckets = [0] * 8
for v in vals:
    buckets[min(7, int(v / 32))] += 1

# white-coat sample region (centre torso, away from hair/trousers)
coat = []
for y in range(int(h * 0.30), int(h * 0.62)):
    for x in range(int(w * 0.40), int(w * 0.60)):
        r, g, b, a = im.getpixel((x, y))
        if a > 128:
            coat.append(lum((r, g, b)))
coat_buckets = [0] * 8
for v in coat:
    coat_buckets[min(7, int(v / 32))] += 1

report = {
    "file": target.name,
    "opaque_pixels": len(opaque),
    "mean_luminance": round(sum(vals) / max(len(vals), 1), 2),
    "luminance_hist_8x32": buckets,
    "pct_above_224": round(100 * sum(buckets[7:]) / max(len(vals), 1), 2),
    "coat_sample_pixels": len(coat),
    "coat_mean": round(sum(coat) / max(len(coat), 1), 2),
    "coat_hist_8x32": coat_buckets,
    "diagnosis": None,
}
report["diagnosis"] = (
    "OVEREXPOSED_TOP_BAND" if report["coat_mean"] > 205 else
    "BANDS_SHOULD_BE_VISIBLE" if 90 < report["coat_mean"] <= 205 else
    "TOO_DARK"
)
out = HERE / ("diag_toon_" + target.stem + ".json")
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False), flush=True)
