from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
NEW = HERE / "rhythm-regression-frames-1280" / "rhythm-frame-t048-impact-HIT.png"
OLD = BAKE / "engine-optimization" / "regression-frames" / "rhythm-frame-t048-impact-HIT.png"

a = Image.open(NEW).convert("RGB")
b = Image.open(OLD).convert("RGB")
d = ImageChops.difference(a, b)
print("size", a.size, b.size)
for name, box in [("all", (0, 0, 1280, 720)), ("above_hand", (0, 0, 1280, 540)),
                  ("top_left", (0, 0, 200, 200)), ("center_bg", (500, 200, 800, 320))]:
    c = d.crop(box)
    px = list(c.get_flattened_data())
    mx = max(max(p) for p in px)
    nz = sum(1 for p in px if p != (0, 0, 0))
    mean = sum(sum(p) for p in px) / (len(px) * 3)
    hist = Counter(max(p) for p in px)
    print(name, "nz=%d/%d max=%d mean=%.4f top=%s" %
          (nz, len(px), mx, mean, hist.most_common(8)))
