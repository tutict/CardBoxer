"""挑几帧放大并排：同帧号上排=手写兜底，下排=烘焙表。"""

import glob
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

OLD, NEW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
PICK = [int(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else [1, 3, 5, 8, 11, 14]
CROP = (540, 300, 800, 545)
SCALE = 2.0
FONT = r"C:\Windows\Fonts\msyh.ttc"


def load(d):
    files = sorted(glob.glob(os.path.join(d, "strip_*.png")),
                   key=lambda p: int(re.search(r"strip_(\d+)", p).group(1)))
    return [Image.open(f).convert("RGB") for f in files]


old, new = load(OLD), load(NEW)
w = int((CROP[2] - CROP[0]) * SCALE)
h = int((CROP[3] - CROP[1]) * SCALE)
PAD, LAB = 8, 30
cols = len(PICK)
sheet = Image.new("RGB", (cols * (w + PAD) + PAD, 2 * (LAB + h + PAD) + PAD), (10, 11, 18))
dr = ImageDraw.Draw(sheet)
f = ImageFont.truetype(FONT, 20)
f2 = ImageFont.truetype(FONT, 15)

titles = [("接线前 · 手写兜底", (250, 168, 74)), ("接线后 · Blender 表", (120, 205, 250))]
for r, (t, col) in enumerate(titles):
    y0 = PAD + r * (LAB + h + PAD)
    dr.text((PAD, y0 + 4), t, font=f, fill=col)
    for i, fr in enumerate(PICK):
        x = PAD + i * (w + PAD)
        img = (old if r == 0 else new)[fr - 1].crop(CROP).resize((w, h), Image.LANCZOS)
        sheet.paste(img, (x, y0 + LAB))
        dr.rectangle([x - 1, y0 + LAB - 1, x + w, y0 + LAB + h], outline=(40, 42, 56), width=1)
        dr.text((x + 4, y0 + LAB + h - 20), "第 %d 帧" % fr, font=f2, fill=(150, 150, 170))

sheet.save(OUT)
print("saved", OUT, sheet.size)
