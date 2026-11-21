"""G 路线：把 8 组侧向视角探针帧裁到玩家侧 ROI 拼成对照板。

用法：python make_side_board.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "side_probe"
BOARDS = HERE / "boards"
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")

# 玩家侧 3D 角色 + 一小段地面，保留对手方向参照。
ROI = (250, 250, 620, 545)
NAMES = [
    ("y000-f0", "正视 / 不翻"),
    ("y000-f1", "正视 / 镜像"),
    ("ym35-f0", "-35° / 不翻"),
    ("ym35-f1", "-35° / 镜像"),
    ("ym55-f0", "-55° / 不翻"),
    ("ym55-f1", "-55° / 镜像"),
    ("yp35-f0", "+35° / 不翻"),
    ("yp55-f0", "+55° / 不翻"),
]


def font(sz: int):
    if FONT_PATH.is_file():
        return ImageFont.truetype(str(FONT_PATH), sz)
    return ImageFont.load_default()


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    ims = {}
    for name, _ in NAMES:
        p = SHOTS / f"side-{name}.png"
        if not p.is_file():
            print("MISSING", p)
            return 1
        ims[name] = Image.open(p).convert("RGB").crop(ROI)

    cw, ch = ROI[2] - ROI[0], ROI[3] - ROI[1]
    scale = 0.85
    w, h = int(cw * scale), int(ch * scale)
    pad, label_h, cols = 12, 30, 4
    rows = (len(NAMES) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * (w + pad) + pad,
                               rows * (h + label_h + pad) + pad), (20, 24, 34))
    d = ImageDraw.Draw(canvas)
    f = font(17)
    for i, (name, label) in enumerate(NAMES):
        r, c = divmod(i, cols)
        x, y = pad + c * (w + pad), pad + r * (h + label_h + pad)
        canvas.paste(ims[name].resize((w, h)), (x, y))
        d.text((x + 4, y + h + 3), f"{name}  {label}", font=f,
               fill=(150, 220, 200))
    out = BOARDS / "G-侧身角度八宫格.png"
    canvas.save(out)
    print(f"BOARD {out} {canvas.width}x{canvas.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
