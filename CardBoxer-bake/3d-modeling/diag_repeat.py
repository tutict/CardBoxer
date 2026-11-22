"""Locate the stance-vs-repeat pixel difference before touching any threshold."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent


def flat(p):
    im = Image.open(p).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


a = flat(HERE / "3d-stance.png")
b = flat(HERE / "3d-stance_repeat.png")
d = ImageChops.difference(a, b)
print("bbox", d.getbbox())
grey = d.convert("L")
changed = [(x, y) for y in range(512) for x in range(512) if grey.getpixel((x, y)) > 6]
print("changed_px", len(changed))
print("max_delta", max(grey.get_flattened_data()))
if changed:
    print("rows", Counter(y for _, y in changed).most_common(12))
    print("cols", Counter(x for x, _ in changed).most_common(12))
    for x, y in changed[:20]:
        print(f"  ({x},{y}) A={a.getpixel((x,y))} B={b.getpixel((x,y))}")
    print("A-color-top", Counter(a.getpixel(p) for p in changed).most_common(8))
    print("B-color-top", Counter(b.getpixel(p) for p in changed).most_common(8))
