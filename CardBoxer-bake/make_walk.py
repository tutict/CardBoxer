"""Assemble the walk-strip captures into a contact sheet with a fixed ruler.

The camera does not move, so a planted foot must stay on the same tick in every
frame. Ticks are drawn at a fixed screen x, which is a world-fixed reference.
"""

import glob
import os
import sys

from PIL import Image, ImageDraw

SRC = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\tutic\AppData\Local\Temp\fa-walk"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"D:\Projects\CardBoxer\CardBoxer-bake\walk-frame-by-frame.png"
COLS = int(sys.argv[3]) if len(sys.argv) > 3 else 6
X0, X1 = 300, 660
Y0, Y1 = 270, 580
SCALE = 0.62
if len(sys.argv) > 4:
    SCALE = float(sys.argv[4])
if len(sys.argv) > 5:
    X0, X1 = int(sys.argv[5]), int(sys.argv[6])
TICK = 20  # screen px between ticks


def numeric(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return int("".join(ch for ch in stem if ch.isdigit()) or 0)


files = sorted(glob.glob(os.path.join(SRC, "*.png")), key=numeric)
if len(sys.argv) > 7:
    files = files[: int(sys.argv[7])]
if not files:
    raise SystemExit("no frames in " + SRC)

w = int((X1 - X0) * SCALE)
h = int((Y1 - Y0) * SCALE)
rows = (len(files) + COLS - 1) // COLS
sheet = Image.new("RGB", (w * COLS, h * rows), (14, 16, 20))
draw = ImageDraw.Draw(sheet)

for i, path in enumerate(files):
    im = Image.open(path).convert("RGB").crop((X0, Y0, X1, Y1)).resize((w, h), Image.LANCZOS)
    tile = ImageDraw.Draw(im)
    # 地面 y=520（游戏坐标）在裁剪窗口里的位置不变，机位也不动 —— 刻度就是世界刻度。
    for gx in range(X0, X1, TICK):
        px = int((gx - X0) * SCALE)
        tile.line([(px, 0), (px, h)], fill=(255, 255, 255, 18) if gx % (TICK * 5) else (255, 210, 120), width=1)
    tile.text((4, 4), path.rsplit("_", 1)[-1].split(".")[0], fill=(220, 230, 240))
    sheet.paste(im, ((i % COLS) * w, (i // COLS) * h))

draw = ImageDraw.Draw(sheet)
for c in range(COLS + 1):
    draw.line([(c * w, 0), (c * w, h * rows)], fill=(60, 70, 84), width=1)
for r in range(rows + 1):
    draw.line([(0, r * h), (w * COLS, r * h)], fill=(60, 70, 84), width=1)

sheet.save(OUT)
print("wrote", OUT, sheet.size, len(files), "frames")
