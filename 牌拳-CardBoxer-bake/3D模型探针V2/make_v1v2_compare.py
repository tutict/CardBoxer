"""Side-by-side, same-height comparison of the two 3D probe previews."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / "3D模型探针" / "artifact_02.png"
V2 = HERE / "artifact_01.png"
OUT = HERE / "V1-V2造型对照.png"

H = 560
PAD = 18
TOP = 42

imgs = []
for p in (V1, V2):
    im = Image.open(p).convert("RGBA")
    w = round(im.width * H / im.height)
    im = im.resize((w, H), Image.LANCZOS)
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    imgs.append(bg.convert("RGB"))

W = sum(i.width for i in imgs) + PAD * 3
canvas = Image.new("RGB", (W, H + TOP + PAD), (244, 245, 247))
d = ImageDraw.Draw(canvas)
x = PAD
for im, label in zip(imgs, ("V1  panda palette / gloves / twin buns",
                            "V2  white cloud-hem coat / no gloves / long hair")):
    d.text((x, 14), label, fill=(30, 34, 40))
    canvas.paste(im, (x, TOP))
    x += im.width + PAD
canvas.save(OUT)
print(f"COMPARE_OK {OUT.name} {canvas.width}x{canvas.height} bytes={OUT.stat().st_size}")
