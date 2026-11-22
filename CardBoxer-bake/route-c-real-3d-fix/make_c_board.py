"""C 路线探针对照板：站架恒等 / 平滑 vs 刚性 / 三档 / 侧视。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CELL, MARGIN, HEAD, LABEL = 330, 20, 62, 30
BG, PANEL = (28, 31, 42), (42, 47, 62)


def font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


FH, FL, FS = font(23), font(18), font(15)
ROWS = [
    ("站架恒等 & 权重 A/B（同一 jab#8 帧）",
     [("c-rest-unposed.png", "未变形 baseline"),
      ("c-stance-driven.png", "走完整驱动链 delta=0"),
      ("c-jab-rigid.png", "刚性权重 A（旧）"),
      ("c-jab-smooth.png", "平滑权重 B（C 路线）")]),
    ("三档动作 & 侧视体积",
     [("c-jab-f007.png", "刺拳 jab#8 (真 3D 网格)"),
      ("c-cross-f011.png", "交叉反击 cross#12"),
      ("c-wave-f018.png", "气功波 wave#19"),
      ("c-stance-angle55.png", "站架 55° 侧视")]),
]
W = MARGIN * 2 + 4 * CELL
H = HEAD + 2 * (LABEL + CELL + 30)
sheet = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(sheet)
d.text((MARGIN, 14), "C 路线 · A-pose rest 骨架 + 连续壳平滑权重 + 增量驱动",
       font=FH, fill=(236, 240, 250))
for r, (title, items) in enumerate(ROWS):
    top = HEAD + r * (LABEL + CELL + 30)
    d.text((MARGIN, top - 26), title, font=FL, fill=(240, 214, 160))
    for c, (fn, label) in enumerate(items):
        p = HERE / "frames" / fn
        assert p.is_file(), f"missing {p}"
        im = Image.open(p).convert("RGBA").resize((CELL, CELL), Image.LANCZOS)
        bg = Image.new("RGBA", (CELL, CELL), PANEL + (255,))
        bg.alpha_composite(im)
        x = MARGIN + c * CELL
        sheet.paste(bg.convert("RGB"), (x, top + LABEL))
        d.text((x + 4, top + LABEL + CELL + 5), label, font=FS,
               fill=(184, 194, 214))
out = HERE / "C-route-probe-comparison-board.png"
sheet.save(out)
print(f"C_BOARD_OK {out.name} {out.stat().st_size} B size={sheet.size}")
