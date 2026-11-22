"""Build a 2x4 labelled contact sheet from the eight 3D representative renders.

    C:/Users/tutic/IdeaProjects/Fantasy-Agent/.venv/Scripts/python.exe \
        D:/Projects/CardBoxer/CardBoxer-bake/3d-modeling/make_contact_sheet_3d.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CELL = 256
LABEL_H = 26
TITLE_H = 34
COLS = 4

LABELS = {
    "3d-stance.png": "stance  |  frame 0  |  player",
    "3d-jab_impact.png": "jab  |  impact f7",
    "3d-sweep_impact.png": "sweep  |  impact f13",
    "3d-throw_impact.png": "throw  |  impact f9",
    "3d-hit_heavy_mid.png": "hit_heavy  |  f15",
    "3d-stance_enemy.png": "stance  |  enemy palette",
    "3d-stance_angle55.png": "stance  |  camera 55 deg (depth)",
    "3d-stance_repeat.png": "stance  |  repeat (determinism)",
}

shots = json.loads((HERE / "render_manifest.json").read_text(encoding="utf-8"))["shots"]
files = [s["file"] for s in shots]
assert len(files) == 8, f"expected 8 shots, got {len(files)}"

try:
    font = ImageFont.load_default(size=14)
except TypeError:
    font = ImageFont.load_default()

rows = (len(files) + COLS - 1) // COLS
W, H = COLS * CELL, TITLE_H + rows * (CELL + LABEL_H)
sheet = Image.new("RGB", (W, H), (250, 250, 250))
draw = ImageDraw.Draw(sheet)
draw.text((10, 9), "CardBoxer 3D - Blender 5.2.3 - 13-bone armature + skinned round-section body",
          fill=(25, 25, 30), font=font)

for i, name in enumerate(files):
    im = Image.open(HERE / name).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    tile = Image.alpha_composite(bg, im).convert("RGB").resize((CELL, CELL), Image.LANCZOS)
    cx, cy = (i % COLS) * CELL, TITLE_H + (i // COLS) * (CELL + LABEL_H)
    sheet.paste(tile, (cx, cy))
    draw.rectangle((cx, cy + CELL, cx + CELL, cy + CELL + LABEL_H), fill=(238, 238, 240))
    draw.text((cx + 6, cy + CELL + 6), LABELS.get(name, name), fill=(20, 20, 25), font=font)
    draw.line((cx + CELL - 1, cy, cx + CELL - 1, cy + CELL + LABEL_H), fill=(215, 215, 220))

out = HERE / "3d-eight-frame-comparison.png"
sheet.save(out)
print(f"CONTACT_SHEET_OK {out} {sheet.size[0]}x{sheet.size[1]} bytes={out.stat().st_size}")
