"""V3 / V4 same-camera comparison boards.

Two deliverables:
  V3-V4-model-comparison.png   full body + face + upper body, 3 rows x 2 columns
  V3-V4-face-detail.png   face close-ups only, bigger, for judging the face model

All Blender renders come from render_character.py with identical cameras and
lights, so any difference is the model, not the framing.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
V3 = BAKE / "3d-model-probe-v3"

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
        im = f.convert("RGBA")
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (*bg, 255))
    canvas.alpha_composite(im)
    return canvas.convert("RGB")


def cell(im, x, y, w, h, src: Path, bg, label):
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x, y, x + w, y + h), radius=8, fill=CELL, outline=(72, 78, 96), width=1)
    pad = 10
    inner = min(w, h) - 2 * pad
    pic = on_bg(src, inner, bg)
    im.paste(pic, (x + (w - inner) // 2, y + pad))
    text(im, x + 12, y + h - 26, label, 13, SUB)


def main():
    rows = [
        ("全身 · 服务预览", V3 / "artifact_02.png", HERE / "artifact_02.png", (255, 255, 255), ""),
        ("脸模 · 正面特写", HERE / "v3-face-front.png", HERE / "v4-face-front.png", (58, 62, 74), "同相机 / 同灯光"),
        ("上半身 · 结构与配饰", HERE / "v3-upper.png", HERE / "v4-upper.png", (58, 62, 74), "同相机 / 同灯光"),
    ]
    for _, a, b, _, _ in rows:
        for p in (a, b):
            assert p.is_file(), f"missing render: {p}"

    W, H = 1280, 1260  # 第三行格子到 y=1200，底部说明必须留出空隙，别压住格子标签
    board = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(board)
    d.rectangle((40, 40, W - 40, 42), fill=ACCENT)
    text(board, 40, 56, "V3 → V4 造型对照", 34, INK, True)
    text(board, 40, 100, "同相机 / 同灯光 / 同尺度 · 保留 PBR 原材质（工程师选的是服务预览，不是 toon 立绘）", 14, SUB)

    cw, ch, gap = 320, 340, 24
    x0, x1 = 130, 130 + cw + gap
    for i, (title, a, b, bg, note) in enumerate(rows):
        y = 140 + i * (ch + 20)
        text(board, 30, y + ch // 2 - 12, "V3", 18, (190, 198, 214), True)
        cell(board, x0, y, cw, ch, a, bg, "V3 · " + title)
        cell(board, x1, y, cw, ch, b, bg, "V4 · " + title + (" · " + note if note else ""))

    rx = x1 + cw + 34
    d.rounded_rectangle((rx, 140, W - 30, 140 + 3 * (ch + 20) - 20),
                        radius=8, fill=(32, 35, 44), outline=(72, 78, 96), width=1)
    text(board, rx + 18, 158, "V4 本轮改了什么", 20, ACCENT, True)
    items = [
        ("脸模", "杏形眼 / 分层虹膜 / 双高光 / 清晰睫毛 / 下颌线 / 均匀肤色"),
        ("领口", "金色滚边立领 + 短外袍式披肩领"),
        ("襟片", "玄黑不对称前襟 + 白色叶片云纹印花"),
        ("纽扣", "红盘扣保留 + 太极圆扣 + 金乌领纹"),
        ("挂饰", "绳结 / 流苏 / 符牌 / 长命锁腰牌 / 挂穗"),
        ("头部", "白发箍 + 一对红色几何角 + 侧花朵结 + 银耳环"),
        ("手部", "半指缠手带 + 银环镯 + 深色护腕（仍无拳套）"),
        ("保留", "靛蓝云纹下摆 / 不对称下摆 / 厚底靴 / 电光青点缀"),
    ]
    yy = 196
    for k, v in items:
        text(board, rx + 18, yy, k, 15, ACCENT, True)
        # 手动折行，控制宽度
        line, lines = "", []
        for ch_ in v:
            line += ch_
            if len(line) >= 13:
                lines.append(line)
                line = ""
        if line:
            lines.append(line)
        for j, ln in enumerate(lines[:3]):
            text(board, rx + 74, yy + j * 20, ln, 13, (206, 214, 228))
        yy += max(20 * len(lines[:3]), 22) + 16

    text(board, 40, H - 34, "离线渲染对照 · 非游戏内 UI · 脚本只证明同相机，不证明好看", 12, SUB)
    board.save(HERE / "V3-V4-model-comparison.png")

    # 脸模放大：两张 512 并排，方便逐像素看五官
    fw, fh = 512, 560
    face = Image.new("RGB", (fw * 2 + 30, fh), BG)
    for i, (p, tag) in enumerate([(HERE / "v3-face-front.png", "V3 脸模"),
                                  (HERE / "v4-face-front.png", "V4 脸模")]):
        x = 10 + i * (fw + 10)
        face.paste(on_bg(p, fw, (58, 62, 74)), (x, 40))
        text(face, x + 8, 10, tag, 22, INK, True)
    face.save(HERE / "V3-V4-face-detail.png")
    print("COMPARE_OK", board.size, face.size)


if __name__ == "__main__":
    main()
