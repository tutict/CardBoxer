"""V3 / V4 / V4b three-way board, same cameras and lights throughout.

  rows: full body (service preview) / face close-up / upper body
  cols: V3 baseline / V4 improved / V4b corrected
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
V3 = BAKE / "3D模型探针V3"
V4 = BAKE / "3D模型探针V4"

FONT = Path("C:/Windows/Fonts/msyh.ttc")
BOLD = Path("C:/Windows/Fonts/msyhbd.ttc")
BG = (26, 28, 34)
CELL = (36, 39, 48)
ACCENT = (70, 210, 230)
INK = (232, 236, 244)
SUB = (150, 160, 180)


def fnt(size, bold=False):
    p = BOLD if bold else FONT
    return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default()


def text(im, x, y, s, size=14, color=INK, bold=False):
    ImageDraw.Draw(im).text((x, y), s, font=fnt(size, bold), fill=color)


def on_bg(path: Path, size: int, bg):
    with Image.open(path) as f:
        im = f.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (*bg, 255))
    canvas.alpha_composite(im)
    return canvas.convert("RGB")


ROWS = [
    # 第 1 行改用 Blender 同相机全身渲染：三版口径完全一致，
    # 也避开 V4b 服务预览 PNG 下载超时造成的缺件。
    ("全身 · 同相机渲染", [
        (V4 / "v3-front.png", (58, 62, 74)),
        (V4 / "v4-front.png", (58, 62, 74)),
        (HERE / "v4b-front.png", (58, 62, 74)),
    ]),
    ("脸模 · 正面特写", [
        (V4 / "v3-face-front.png", (58, 62, 74)),
        (V4 / "v4-face-front.png", (58, 62, 74)),
        (HERE / "v4b-face-front.png", (58, 62, 74)),
    ]),
    ("上半身 · 结构与配饰", [
        (V4 / "v3-upper.png", (58, 62, 74)),
        (V4 / "v4-upper.png", (58, 62, 74)),
        (HERE / "v4b-upper.png", (58, 62, 74)),
    ]),
]
COLS = ["V3 基准", "V4 优化", "V4b 修正"]


def main():
    for _, items in ROWS:
        for p, _ in items:
            assert p.is_file(), f"missing render: {p}"

    W, H = 1160, 1340  # 第三行格子到 y=1204，notes 与底部说明都要留够空隙
    board = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(board)
    d.rectangle((30, 34, W - 30, 36), fill=ACCENT)
    text(board, 30, 48, "V3 → V4 → V4b 三版造型对照", 30, INK, True)
    text(board, 30, 90, "同相机 / 同灯光 / 同尺度 · 保留 PBR 原材质", 14, SUB)

    cw, ch, gap = 340, 336, 20
    x0 = 30
    for j, name in enumerate(COLS):
        text(board, x0 + j * (cw + gap) + 6, 118, name, 17,
             ACCENT if j == 2 else (190, 198, 214), True)

    for i, (title, items) in enumerate(ROWS):
        y = 148 + i * (ch + 24)
        for j, (p, bg) in enumerate(items):
            x = x0 + j * (cw + gap)
            d.rounded_rectangle((x, y, x + cw, y + ch), radius=8,
                                fill=CELL, outline=(72, 78, 96), width=1)
            inner = cw - 20
            board.paste(on_bg(p, inner, bg), (x + 10, y + 8))
            text(board, x + 12, y + ch - 24, title, 12, SUB)

    yy = 148 + 3 * (ch + 24) + 12
    notes = [
        "V4 达成：分层琥珀虹膜 / 清晰睫毛 / 明黄披肩领 / 太极圆扣 / 绳结流苏 / 银环镯",
        "V4 偏差：短袖露上臂（违反全覆盖）、红色双角过贴叶瞬光、黑色不对称襟片没生成",
        "V4b 只改三处：全身长袖、头饰弱化为小发夹、黑襟片与白叶纹前置强化；脸模不动",
    ]
    for n in notes:
        text(board, 32, yy, n, 13, (206, 214, 228))
        yy += 22
    text(board, 30, H - 28, "离线渲染对照 · 非游戏内 UI · 脚本只证明同相机，不证明好看", 12, SUB)
    board.save(HERE / "V3-V4-V4b-三版对照.png")
    print("THREEWAY_OK", board.size)


if __name__ == "__main__":
    main()
