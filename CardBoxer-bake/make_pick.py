"""Pick specific strip frames, crop and scale them into one row."""

import os
import sys

from PIL import Image, ImageDraw

SRC = r"C:\Users\tutic\AppData\Local\Temp\fa-sweep"
OUT = r"D:\Projects\CardBoxer\CardBoxer-bake\sweep-three-frames.png"
PICK = [1, 6, 8, 10, 13, 16]
X0, X1, Y0, Y1 = 500, 790, 290, 560
SCALE = 1.6

tiles = []
for i in PICK:
    path = os.path.join(SRC, "strip_%02d.png" % i)
    im = Image.open(path).convert("RGB").crop((X0, Y0, X1, Y1))
    im = im.resize((int((X1 - X0) * SCALE), int((Y1 - Y0) * SCALE)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.text((8, 8), "f%d" % i, fill=(255, 232, 150))
    tiles.append(im)

w, h = tiles[0].size
sheet = Image.new("RGB", (w * len(tiles), h), (12, 14, 18))
for n, t in enumerate(tiles):
    sheet.paste(t, (n * w, 0))
sheet.save(OUT)
print("wrote", OUT, sheet.size)
