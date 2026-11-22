"""G 路线：6 组反向站架偏置对照板（玩家侧放大）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "side_stance_scan"
BOARDS = HERE / "boards"
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")
ROI = (270, 265, 570, 545)
NAMES = ["r0-flip-all", "r1-flip-fore", "r2-flip-upper",
         "r3-fonly-neg", "r4-both-neg", "r5-guard-high"]


def font(sz: int):
    if FONT_PATH.is_file():
        return ImageFont.truetype(str(FONT_PATH), sz)
    return ImageFont.load_default()


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    cw, ch = ROI[2] - ROI[0], ROI[3] - ROI[1]
    w, h = 330, int(ch * 330 / cw)
    pad, label_h, cols = 12, 30, 3
    rows = (len(NAMES) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * (w + pad) + pad,
                               rows * (h + label_h + pad) + pad), (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = font(17)
    for i, name in enumerate(NAMES):
        p = SHOTS / f"stance-{name}.png"
        if not p.is_file():
            print("MISSING", p)
            return 1
        r, c = divmod(i, cols)
        x, y = pad + c * (w + pad), pad + r * (h + label_h + pad)
        canvas.paste(Image.open(p).convert("RGB").crop(ROI).resize((w, h)),
                     (x, y))
        d.text((x + 4, y + h + 3), name, font=f, fill=(150, 220, 200))
    out = BOARDS / "G-side-view-reverse-stance-scan.png"
    canvas.save(out)
    print(f"BOARD {out} {canvas.width}x{canvas.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
