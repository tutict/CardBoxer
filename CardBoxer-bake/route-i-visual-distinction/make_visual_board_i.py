"""I 路线看图：把 on / plain 两帧的左右角色裁出来放大并排。

上部 2×2：玩家 on / 对手 on / 玩家 plain / 对手 plain；
下部两张 600×338 全景缩略，用来判断「是否一眼可分」。
输出 boards/I-visual-distinction-A-B.png。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
H = HERE.parent / "route-h-two-sided-3d-combat"
SHOTS = HERE / "shots" / "visual_ab"
OUT = HERE / "boards" / "I-visual-distinction-A-B.png"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
ROI = json.loads((H / "data" / "roi_h.json").read_text(
    encoding="utf-8"))["boxes"]


def crop(im: Image.Image, box, size=(126, 265)) -> Image.Image:
    w, h = size
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    return im.crop((cx - w // 2, cy - h // 2,
                    cx - w // 2 + w, cy - h // 2 + h))


def main() -> int:
    on = Image.open(SHOTS / "vis-on.png").convert("RGB")
    plain = Image.open(SHOTS / "vis-plain.png").convert("RGB")
    z = 2
    w, h = 126 * z, 265 * z
    pad, label = 24, 34
    tw, th = 600, 338
    wide = 2 * tw + 3 * pad
    tall = 2 * (h + label) + 3 * pad + th + 50
    canvas = Image.new("RGB", (wide, tall), (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 20) if FONT.is_file() \
        else ImageFont.load_default()
    x0 = (wide - (2 * w + pad)) // 2
    x1 = x0 + w + pad
    y0 = pad
    y1 = pad + h + label + pad
    cells = [
        (crop(on, ROI[0]), "玩家 · 视觉开 on", x0, y0, (160, 225, 205)),
        (crop(on, ROI[1]), "对手 · 视觉开 on", x1, y0, (240, 170, 150)),
        (crop(plain, ROI[0]), "玩家 · 视觉关 plain", x0, y1,
         (160, 225, 205)),
        (crop(plain, ROI[1]), "对手 · 视觉关 plain", x1, y1,
         (240, 170, 150)),
    ]
    for im, text, x, y, col in cells:
        canvas.paste(im.resize((w, h), Image.LANCZOS), (x, y))
        d.text((x + 6, y + h + 4), text, font=f, fill=col)
    ty = y1 + h + label + pad
    for i, (im, text) in enumerate([
            (on, "全景 · on（视觉开）"),
            (plain, "全景 · plain（视觉关 / H 原样）")]):
        x = pad + i * (tw + pad)
        canvas.paste(im.resize((tw, th), Image.LANCZOS), (x, ty))
        d.text((x + 6, ty + th + 2), text, font=f, fill=(180, 190, 210))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT)
    print("WROTE", OUT.name, OUT.stat().st_size, "B", canvas.size)
    print("VISUAL_BOARD_I_OK" if OUT.stat().st_size > 50000
          else "VISUAL_BOARD_I_FAILED")
    return 0 if OUT.stat().st_size > 50000 else 1


if __name__ == "__main__":
    raise SystemExit(main())
