"""把探针帧贴到深色底上做对照板（透明 PNG 直接看会丢主体）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CELL = 420
MARGIN, HEAD = 20, 60


def font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F = font(22)
files = ["stance_f000.png", "jab_f007.png", "wave_f018.png"]
labels = ["站架 stance", "刺拳 jab #8", "气功波 wave #19"]
sheet = Image.new("RGB", (MARGIN * 2 + 3 * CELL, HEAD + CELL + 40), (28, 31, 42))
d = ImageDraw.Draw(sheet)
d.text((MARGIN, 14), "新 3D 建模人物 · 骨架驱动探针（对手怪 V1）",
       font=F, fill=(232, 236, 246))
for i, (fn, label) in enumerate(zip(files, labels)):
    p = HERE / "frames" / "foe" / fn
    im = Image.open(p).convert("RGBA").resize((CELL, CELL), Image.LANCZOS)
    bg = Image.new("RGBA", (CELL, CELL), (38, 42, 56, 255))
    bg.alpha_composite(im)
    x = MARGIN + i * CELL
    sheet.paste(bg.convert("RGB"), (x, HEAD))
    d.text((x + 8, HEAD + CELL + 8), label, font=F, fill=(190, 198, 216))
out = HERE / "驱动探针-对手怪.png"
sheet.save(out)
print(f"PROBE_SHEET_OK {out.name} {out.stat().st_size} B")
