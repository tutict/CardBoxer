"""三行对照板：玩家 puppet / 对手怪 puppet / 对手怪真 3D 网格驱动（证伪）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CELL = 340
MARGIN, HEAD, ROWH = 20, 62, CELL + 62
BG = (30, 34, 46)
PANEL = (42, 47, 62)


def font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


FH, FL, FS = font(23), font(18), font(16)
ROWS = [
    ("玩家 V4b · 3D 立绘骨骼 puppet", HERE / "frames/puppet_player", (240, 214, 160)),
    ("对手怪 V1 · 3D 立绘骨骼 puppet", HERE / "frames/puppet_foe", (240, 214, 160)),
    ("对手怪 V1 · 真 3D 网格 + 刚性权重（证伪）", HERE / "frames/foe", (238, 138, 138)),
]
FILES = ["stance_f000.png", "jab_f007.png", "wave_f018.png"]
COLS = ["站架 stance", "刺拳 jab #8", "气功波 wave #19"]

sheet = Image.new("RGB", (MARGIN * 2 + 3 * CELL, HEAD + 3 * ROWH), BG)
d = ImageDraw.Draw(sheet)
d.text((MARGIN, 12), "新 3D 建模人物 · 攻击驱动三路对照",
       font=FH, fill=(236, 240, 250))
for r, (title, folder, color) in enumerate(ROWS):
    top = HEAD + r * ROWH
    d.text((MARGIN, top - 26), title, font=FL, fill=color)
    for c, (fn, col) in enumerate(zip(FILES, COLS)):
        p = folder / fn
        assert p.is_file(), f"missing {p}"
        im = Image.open(p).convert("RGBA").resize((CELL, CELL), Image.LANCZOS)
        bg = Image.new("RGBA", (CELL, CELL), PANEL + (255,))
        bg.alpha_composite(im)
        x = MARGIN + c * CELL
        sheet.paste(bg.convert("RGB"), (x, top))
        d.text((x + 6, top + CELL + 6), col, font=FS, fill=(184, 194, 214))

out = HERE / "驱动三路对照.png"
sheet.save(out)
print(f"PROBE_COMPARE_OK {out.name} {out.stat().st_size} B")
