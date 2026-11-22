"""Walking as a loopable GIF with a world-fixed ruler burned in.

The camera does not move, so the ruler is a fixed reference: a foot that is
planted must stay on the same tick while the body slides past it.
"""

import glob
import os
import sys

from PIL import Image, ImageDraw

SRC = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\tutic\AppData\Local\Temp\fa-walk"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"D:\Projects\CardBoxer\CardBoxer-bake\walk.gif"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 30
X0, X1 = 380, 640
Y0, Y1 = 280, 570
SCALE = 0.9
TICK = 20


def numeric(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return int("".join(ch for ch in stem if ch.isdigit()) or 0)


files = sorted(glob.glob(os.path.join(SRC, "walk_*.png")), key=numeric)[:LIMIT]
if not files:
    raise SystemExit("no frames in " + SRC)

w = int((X1 - X0) * SCALE)
h = int((Y1 - Y0) * SCALE)
frames = []
for i, path in enumerate(files):
    im = Image.open(path).convert("RGB").crop((X0, Y0, X1, Y1)).resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    for gx in range(X0, X1, TICK):
        px = int((gx - X0) * SCALE)
        d.line([(px, 0), (px, h)], fill=(250, 200, 110) if gx % (TICK * 5) == 0 else (52, 58, 70), width=1)
    d.text((5, 5), "%02d" % i, fill=(230, 236, 244))
    frames.append(im)

pal = frames[0].quantize(colors=200, method=Image.MEDIANCUT)
frames = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=33,
               loop=0, optimize=True)
print("wrote", OUT, (w, h), len(frames), "frames", os.path.getsize(OUT) // 1024, "KB")
