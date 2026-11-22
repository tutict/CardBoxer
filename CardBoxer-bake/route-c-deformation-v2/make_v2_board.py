"""出两张板：定稿 A/B 对照 + 定稿关键帧。数值全部从 c2_build.json 现读。

定稿对照只变一个变量（arm-only 增益 x1.0 -> x1.5），权重 / 骨架 / 相机
全部相同。V2（领地修正）已被证伪，不进定稿图。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"
BG = (24, 29, 40)
CARD = (32, 38, 51)
FG = (236, 240, 250)
MUTED = (150, 162, 180)
ACCENT = (240, 214, 160)


def font(size, bold=False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc",) if bold else (
        r"C:\Windows\Fonts\msyh.ttc",)
    for p in names + (r"C:\Windows\Fonts\msyh.ttc",):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


FH, FL, FS, FT = font(27, True), font(19, True), font(15), font(13)


def load(name, size):
    p = FRAMES / name
    im = Image.open(p).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    assert im.getbbox() is not None, f"blank {p}"
    return im


def cell(board, im, x, y, size, label, sub=""):
    d = ImageDraw.Draw(board)
    d.rounded_rectangle((x - 6, y - 6, x + size + 6, y + size + 6),
                        radius=8, fill=CARD)
    board.alpha_composite(im, (x, y))
    d.text((x + 2, y + size + 10), label, font=FS, fill=FG)
    if sub:
        d.text((x + 2, y + size + 30), sub, font=FT, fill=MUTED)


def metrics_for(report, card, frame):
    for r in report["all_frames"]["rows"]:
        if r["card"] == card and r["frame"] == frame:
            return r
    raise KeyError(f"no metrics for {card}#{frame}")


def board_compare(report):
    rows = [
        ("jab07", "jab", 6, "散牌 · 刺拳 命中帧 #08"),
        ("cross11", "cross", 10, "三连 · 交叉反击 命中帧 #12"),
        ("wave18", "wave", 17, "三同 · 气功波 命中帧 #19"),
    ]
    size, gap, mx, head = 380, 20, 32, 116
    row_h = size + 20 + 52
    w = mx * 2 + size * 2 + gap
    h = head + row_h * len(rows) + 60
    board = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(board)
    d.text((mx, 18), "C 路线 V2 · 变形质量定稿对照", font=FH, fill=FG)
    d.text((mx, 58), "同一份 A-pose 平滑权重 / 同一骨架 / 同一相机，"
                     "只改 arm-only 增益 x1.0 → x1.5", font=FL, fill=ACCENT)
    d.text((mx, 86), "数值 = 该帧手腕簇位移 reach_max_m 与边撕裂 p999_m（现读 c2_build.json）",
           font=FT, fill=MUTED)
    for k, (shot, card, fr, title) in enumerate(rows):
        y = head + k * row_h
        m = metrics_for(report, card, fr)
        a, b = m["V1_base"], m["V1_gain"]
        for j, tag in enumerate(("A_x1", "B_x15")):
            x = mx + j * (size + gap)
            im = load(f"{shot}-{tag}.png", size)
            sub = (f"reach {a['reach_max_m'] if j == 0 else b['reach_max_m']:.4f} m"
                   f"  /  tear p999 "
                   f"{a['tear_p999_m'] if j == 0 else b['tear_p999_m']:.5f} m")
            label = ("A · 原增益 x1.0" if j == 0 else "B · 定稿 x1.5") + "   " + title
            cell(board, im, x, y, size, label, sub)
    out = HERE / "V2-final-comparison-board.png"
    board.convert("RGB").save(out)
    return out


def board_keyframes(report):
    shots = [
        ("stance", None, 0, "站架"),
        ("jab01", "jab", 0, "刺拳 #01 前摇"),
        ("jab07", "jab", 6, "刺拳 #08 命中"),
        ("jab13", "jab", 12, "刺拳 #14 收招"),
        ("cross01", "cross", 0, "交叉反击 #01"),
        ("cross11", "cross", 10, "交叉反击 #12 命中"),
        ("cross21", "cross", 20, "交叉反击 #22"),
        ("wave01", "wave", 0, "气功波 #01"),
        ("wave18", "wave", 17, "气功波 #19 命中"),
        ("wave35", "wave", 34, "气功波 #36"),
    ]
    # head 必须给 y=90 的第三行说明留够空隙：卡片圆角框从 head-6 起画，
    # 104 会把 13px 的说明文字盖掉半截（看图复核过一次）。
    size, gap, mx, head, cols = 290, 16, 30, 148, 4
    row_h = size + 20 + 40
    nrows = (len(shots) + cols - 1) // cols
    w = mx * 2 + cols * size + (cols - 1) * gap
    h = head + row_h * nrows + 56
    board = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(board)
    d.text((mx, 18), "C 路线 V2 · 定稿关键帧（B_x15）", font=FH, fill=FG)
    d.text((mx, 58), "10 个代表帧 + 55° 侧视；全部走引擎同款 72 帧门禁",
           font=FL, fill=ACCENT)
    d.text((mx, 90), "腰间斜片 / 下摆锯齿是生成模型自带的 2,809 壳碎片，本轮未修",
           font=FT, fill=MUTED)
    entries = [(s, c, f, t) for s, c, f, t in shots]
    entries.append(("stance-B_x15-angle55", None, 0, "站架 55° 侧视"))
    for k, (shot, card, fr, title) in enumerate(entries):
        x = mx + (k % cols) * (size + gap)
        y = head + (k // cols) * row_h
        fname = f"{shot}-B_x15.png" if not shot.endswith("angle55") else f"{shot}.png"
        im = load(fname, size)
        sub = ""
        if card is not None:
            m = metrics_for(report, card, fr)["V1_gain"]
            sub = f"reach {m['reach_max_m']:.4f} m / tear {m['tear_p999_m']:.5f} m"
        cell(board, im, x, y, size, title, sub)
    out = HERE / "V2-keyframe-board.png"
    board.convert("RGB").save(out)
    return out


def main() -> int:
    report = json.loads((HERE / "c2_build.json").read_text(encoding="utf-8"))
    a = board_compare(report)
    b = board_keyframes(report)
    for p in (a, b):
        print(f"BOARD {p.name} bytes={p.stat().st_size}")
    print("BOARDS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
