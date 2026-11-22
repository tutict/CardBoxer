"""Assemble the engine-side captures (bot demo) into one GIF plus a contact sheet.

The game writes shot_NN.png at 1280x720 in its own viewport, so nothing here has
to deal with window frames, DPI scaling or occlusion. Frames are named with a
%02d index, which means shot_100 sorts before shot_11 -- sort numerically.

Run with the project venv (the only interpreter on this machine with Pillow).
"""

import glob
import os
import re
import sys

from PIL import Image

SRC = r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.workbuddy\bot"
OUT = r"D:\Projects\CardBoxer\CardBoxer-bake\match-demo.gif"
SHEET = r"D:\Projects\CardBoxer\CardBoxer-bake\demo-keyframes.png"

STEP_MS = 70          # 抓帧的间隔（游戏时间）；实际值从第 4 个参数传
WIDTH = 640           # half of 1280; the arena is 16:9 so height follows
COLORS = 160

# argv: src_dir out_gif sheet_png [step_ms] [width]
if len(sys.argv) > 1:
    SRC = sys.argv[1]
if len(sys.argv) > 2:
    OUT = sys.argv[2]
if len(sys.argv) > 3:
    SHEET = sys.argv[3]
if len(sys.argv) > 4:
    STEP_MS = int(sys.argv[4])
if len(sys.argv) > 5:
    WIDTH = int(sys.argv[5])


def index_of(path):
    m = re.search(r"shot_(\d+)\.png$", path)
    return int(m.group(1)) if m else -1


files = sorted(glob.glob(os.path.join(SRC, "shot_*.png")), key=index_of)
print("frames:", len(files), "first/last:", os.path.basename(files[0]),
      os.path.basename(files[-1]))

frames = []
for f in files:
    im = Image.open(f).convert("RGB")
    w, h = im.size
    frames.append(im.resize((WIDTH, round(h * WIDTH / w)), Image.LANCZOS))
print("frame size:", frames[0].size)

pal = [f.quantize(colors=COLORS, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
       for f in frames]
pal[0].save(OUT, save_all=True, append_images=pal[1:], duration=STEP_MS,
            loop=0, optimize=True, disposal=1)
print("gif:", round(os.path.getsize(OUT) / 1e6, 2), "MB",
      "%.1f s" % (len(frames) * STEP_MS / 1000.0))

cols, rows = 4, 3
picks = [round(i * (len(frames) - 1) / (cols * rows - 1)) for i in range(cols * rows)]
w, h = frames[0].size
tw, th = w // 2, h // 2
sheet = Image.new("RGB", (tw * cols, th * rows), (12, 12, 20))
for n, idx in enumerate(picks):
    sheet.paste(frames[idx].resize((tw, th), Image.LANCZOS),
                ((n % cols) * tw, (n // cols) * th))
sheet.save(SHEET)
print("sheet:", SHEET, sheet.size)
