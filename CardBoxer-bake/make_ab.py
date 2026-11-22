"""同一张牌、同一帧号的 A/B 胶片：旧版（手写姿势）在上，新版（烘焙表）在下。

两个目录的 PNG 都来自 tests/motion_strip.gd 在引擎里逐帧渲染的结果，所以帧号
一一对应，差别只可能来自 fighter.gd。

用法（项目 venv）：
    python make_ab.py <old_dir> <new_dir> <out_png> [card]
"""

import glob
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

OLD = sys.argv[1]
NEW = sys.argv[2]
OUT = sys.argv[3]
CARD = sys.argv[4] if len(sys.argv) > 4 else "uppercut"

BAKED = r"D:\Projects\CardBoxer\CardBoxer\data\card_motion.json"

# 裁切框覆盖该卡所有帧的运动范围（含伸出的拳套与向后坐的重心）。
CROP = (560, 285, 790, 548)
SCALE = 0.62

FONT = r"C:\Windows\Fonts\msyh.ttc"
LABEL_H = 34
PAD = 6


def load(d, pattern="strip_*.png"):
    files = sorted(glob.glob(os.path.join(d, pattern)),
                   key=lambda p: int(re.search(r"strip_(\d+)", p).group(1)))
    return [Image.open(f).convert("RGB").crop(CROP).resize(
        (int((CROP[2] - CROP[0]) * SCALE), int((CROP[3] - CROP[1]) * SCALE)),
        Image.LANCZOS) for f in files]


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


old = load(OLD)
new = load(NEW)
n = min(len(old), len(new))
print("frames old/new:", len(old), len(new), "->", n)

impact = json.load(open(BAKED, encoding="utf-8"))["cards"][CARD]["impact"]
held = json.load(open(BAKED, encoding="utf-8"))["cards"][CARD]["held_frames"]

cw, ch = old[0].size
W = n * (cw + PAD) + PAD
H = (LABEL_H + ch + PAD) * 2 + PAD
sheet = Image.new("RGB", (W, H), (10, 11, 18))
draw = ImageDraw.Draw(sheet)
f_label = font(20)
f_tick = font(13)

rows = [
    ("无表 · 手写兜底（同一站架，关节是手摆的关键帧）", old, (250, 168, 74)),
    ("有表 · Blender 烘焙（停顿帧 + 急停 + 圆弧 + 头部滞后）", new, (120, 205, 250)),
]

for r, (title, frames, color) in enumerate(rows):
    y0 = PAD + r * (LABEL_H + ch + PAD)
    draw.text((PAD + 2, y0 + 6), title, font=f_label, fill=color)
    draw.text((W - 300, y0 + 9),
              "第 %d 帧 = 命中判定" % impact, font=f_tick, fill=(150, 150, 165))
    for i in range(n):
        x = PAD + i * (cw + PAD)
        y = y0 + LABEL_H
        sheet.paste(frames[i], (x, y))
        edge = (250, 90, 90) if (i + 1) == impact else (38, 40, 52)
        draw.rectangle([x - 1, y - 1, x + cw, y + ch], outline=edge, width=2)
        draw.text((x + 2, y + ch - 16), str(i + 1), font=f_tick, fill=(110, 112, 130))

sheet.save(OUT)
print("saved", OUT, sheet.size, "held_frames=%d impact=%d" % (held, impact))
