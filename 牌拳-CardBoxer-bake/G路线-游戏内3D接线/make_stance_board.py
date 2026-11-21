"""G 路线：4 档站架偏置对照板（全帧缩小 + 玩家侧放大两行）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "side_stance"
BOARDS = HERE / "boards"
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")
ROI = (270, 265, 570, 545)
NAMES = [("b0-none", "无偏置 A-pose"), ("b1-light", "轻"),
         ("b2-mid", "中"), ("b3-heavy", "重")]


def font(sz: int):
    if FONT_PATH.is_file():
        return ImageFont.truetype(str(FONT_PATH), sz)
    return ImageFont.load_default()


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    ims = {}
    for name, _ in NAMES:
        p = SHOTS / f"stance-{name}.png"
        if not p.is_file():
            print("MISSING", p)
            return 1
        ims[name] = Image.open(p).convert("RGB")

    cw, ch = ROI[2] - ROI[0], ROI[3] - ROI[1]
    w, h = 320, int(ch * 320 / cw)
    pad, label_h = 14, 32
    canvas = Image.new("RGB", (4 * (w + pad) + pad,
                               2 * (h + label_h + pad) + pad), (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = font(18)
    for i, (name, label) in enumerate(NAMES):
        x = pad + i * (w + pad)
        # 上排：玩家侧放大
        y = pad
        canvas.paste(ims[name].crop(ROI).resize((w, h)), (x, y))
        d.text((x + 4, y + h + 3), f"{name}  {label}", font=f,
               fill=(150, 220, 200))
        # 下排：全帧缩小，看两人相对关系
        y2 = pad + h + label_h + pad
        canvas.paste(ims[name].resize((w, int(720 * w / 1280))), (x, y2))
    out = BOARDS / "G-侧身站架四档对照.png"
    canvas.save(out)
    print(f"BOARD {out} {canvas.width}x{canvas.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
