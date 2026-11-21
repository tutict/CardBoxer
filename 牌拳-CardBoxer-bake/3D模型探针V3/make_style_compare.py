"""Three-stage style comparison: V2 PBR / V3 PBR / V3 toon portrait."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
V2 = HERE.parent / "3D模型探针V2" / "artifact_01.png"
ITEMS = [
    (V2, "V2  PBR / white cloud coat / no ZZZ layer"),
    (HERE / "artifact_02.png", "V3  PBR / + tactical strap + cyan + asymmetric hair"),
    (HERE / "立绘-front.png", "V3  cel-shaded toon / outline / low-sat backdrop"),
]
H, PAD, TOP = 560, 16, 34

imgs = []
for p, label in ITEMS:
    assert p.exists(), f"missing {p}"
    im = Image.open(p).convert("RGBA")
    w = round(im.width * H / im.height)
    im = im.resize((w, H), Image.LANCZOS)
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    imgs.append((bg.convert("RGB"), label, w))

W = sum(w for _, _, w in imgs) + PAD * (len(imgs) + 1)
canvas = Image.new("RGB", (W, H + TOP + PAD), (240, 241, 244))
d = ImageDraw.Draw(canvas)
x = PAD
for im, label, w in imgs:
    d.text((x, 12), label, fill=(28, 32, 38))
    canvas.paste(im, (x, TOP))
    x += w + PAD
out = HERE / "造型三版对照.png"
canvas.save(out)
print(f"STYLE_COMPARE_OK {out.name} {canvas.width}x{canvas.height} bytes={out.stat().st_size}")
