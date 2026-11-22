"""三档动作时间线：每档抽 7 帧，检验「前摇 -> 命中 -> 收招」的连续曲线。"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
IDS = ["jab", "cross", "wave"]
LABELS = {"jab": "散牌 · 刺拳", "cross": "三连 · 交叉反击", "wave": "三同 · 气功波"}
CELL, GAP, MARGIN, HEAD, LABEL = 150, 8, 22, 74, 30
COLS = 7
BG = (28, 31, 42)
PANEL = (42, 47, 62)


def font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


FH, FL, FS = font(24), font(18), font(14)
stats = json.loads((HERE / "gif_stats.json").read_text(encoding="utf-8"))
folder = HERE / "frames" / "puppet_player"
box = tuple(stats["routes"]["player"]["box"])
MOTION = json.loads((HERE.parent.parent / "CardBoxer" / "data/card_motion.json")
                    .read_text(encoding="utf-8"))

W = MARGIN * 2 + COLS * CELL + (COLS - 1) * GAP
H = HEAD + 3 * (LABEL + CELL + 26)
sheet = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(sheet)
d.text((MARGIN, 16), "玩家 V4b · 三档攻击动作时间线（3D 立绘骨骼 puppet）",
       font=FH, fill=(236, 240, 250))

for r, cid in enumerate(IDS):
    top = HEAD + r * (LABEL + CELL + 26)
    n = stats["routes"]["player"]["cards"][cid]["frames"]
    split = MOTION["cards"][cid]["split"]
    d.text((MARGIN, top), f"{LABELS[cid]}   {n} 帧 · 前摇/命中/收招 {split}",
           font=FL, fill=(240, 214, 160))
    picks = [round(i * (n - 1) / (COLS - 1)) for i in range(COLS)]
    files = sorted(folder.glob(f"{cid}_f*.png"),
                   key=lambda p: int(p.stem.split("_f")[1]))
    for c, idx in enumerate(picks):
        im = Image.open(files[idx]).convert("RGBA").crop(box)
        bg = Image.new("RGBA", im.size, PANEL + (255,))
        bg.alpha_composite(im)
        tile = bg.convert("RGB").resize((CELL, CELL), Image.LANCZOS)
        x = MARGIN + c * (CELL + GAP)
        sheet.paste(tile, (x, top + LABEL))
        phase = "前摇" if idx < split[0] else (
            "命中" if idx < split[0] + split[1] else "收招")
        d.text((x + 2, top + LABEL + CELL + 3), f"#{idx + 1:02d} {phase}",
               font=FS, fill=(170, 182, 204))

out = HERE / "player-V4b-motion-timeline.png"
sheet.save(out)
print(f"TIMELINE_OK {out.name} {out.stat().st_size} B size={sheet.size}")
