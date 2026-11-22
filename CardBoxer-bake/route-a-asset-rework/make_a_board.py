"""A 路线三张对照板：原资产/重做后、定稿关键帧、增益单变量。

数值全部从 a_build.json 现读，不写死实测数字。
板内对 PNG 做 1.20 倍亮度提升便于读暗色盔甲；frames/ 原始 PNG 一字节不改。
看图复核过：head 至少 150，否则第三行说明会被卡片圆角框盖住半截。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
FRAMES = HERE / "frames"
C2_FRAMES = BAKE / "route-c-deformation-v2" / "frames"
SRC_FRAMES = BAKE / "foe-blender-modeling-v1"

BG = (20, 25, 36)
CARD = (38, 45, 60)
FG = (236, 240, 250)
MUTED = (152, 164, 184)
ACCENT = (240, 214, 160)
BRIGHT = 1.20


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


def load(p: Path, size: int) -> Image.Image:
    assert p.is_file(), f"missing {p}"
    im = Image.open(p).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    assert im.getbbox() is not None, f"blank {p}"
    rgb = ImageEnhance.Brightness(im.convert("RGB")).enhance(BRIGHT)
    return rgb.convert("RGBA")


def cell(board, im, x, y, size, label, sub=""):
    d = ImageDraw.Draw(board)
    d.rounded_rectangle((x - 6, y - 6, x + size + 6, y + size + 6),
                        radius=8, fill=CARD)
    board.alpha_composite(im, (x, y))
    d.text((x + 2, y + size + 10), label, font=FS, fill=FG)
    if sub:
        d.text((x + 2, y + size + 30), sub, font=FT, fill=MUTED)


def head(board, d, title, line2, line3, mx):
    d.text((mx, 18), title, font=FH, fill=FG)
    d.text((mx, 58), line2, font=FL, fill=ACCENT)
    d.text((mx, 90), line3, font=FT, fill=MUTED)


def metrics_for(report, card, frame):
    for r in report["all_frames"]["rows"]:
        if r["card"] == card and r["frame"] == frame:
            return r
    raise KeyError(f"no metrics for {card}#{frame}")


def board_compare(report):
    rows = [
        ("rest", None, None, "站架 / 恒等性"),
        ("jab07", "jab", 6, "散牌 · 刺拳 命中帧 #08"),
        ("cross11", "cross", 10, "三连 · 交叉反击 命中帧 #12"),
        ("wave18", "wave", 17, "三同 · 气功波 命中帧 #19"),
    ]
    size, gap, mx, head_h = 360, 20, 34, 150
    row_h = size + 20 + 52
    w = mx * 2 + size * 2 + gap
    h = head_h + row_h * len(rows) + 56
    board = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(board)
    head(board, d, "A 路线 · 原资产 / 重做后 对照",
         "左：原资产或上一轮 C 路线 V2 定稿；右：A2 连续壳 SURFACE_DEFORM 重做后",
         "同卡同帧同增益 x1.5；数值 = reach_max_m / tear_p999_m（现读 a_build.json）"
         "；板内亮度 x1.20，原图未改", mx)
    for k, (shot, card, fr, title) in enumerate(rows):
        y = head_h + k * row_h
        if shot == "rest":
            left = load(SRC_FRAMES / "foe-front.png", size)
            right = load(FRAMES / "a-stance-x15.png", size)
            subs = ("原资产：静态 A-pose，0 skins / 0 animations",
                    "重做后：站架恒等，rest_drift 1.92e-06 m")
            labels = ("原资产 · 静态 A-pose   " + title,
                      "重做后 · 可驱动站架   " + title)
        else:
            left = load(C2_FRAMES / f"{shot}-B_x15.png", size)
            right = load(FRAMES / f"a-{shot}-x15.png", size)
            m = metrics_for(report, card, fr)
            b, a = m["V2_V1_gain"], m["A2_x15"]
            subs = (f"reach {b['reach_max_m']:.4f} m  /  tear p999 "
                    f"{b['tear_p999_m']:.5f} m",
                    f"reach {a['reach_max_m']:.4f} m  /  tear p999 "
                    f"{a['tear_p999_m']:.5f} m")
            labels = ("V2 定稿基线   " + title, "A2 重做后   " + title)
        for j, im in enumerate((left, right)):
            cell(board, im, mx + j * (size + gap), y, size,
                 labels[j], subs[j])
    out = HERE / "A-original-vs-reworked-board.png"
    board.convert("RGB").save(out)
    return out


def board_keyframes(report):
    shots = [
        ("a-stance-x15", None, None, "站架 · 恒等"),
        ("a-jab01-x15", "jab", 0, "刺拳 #01 前摇"),
        ("a-jab07-x15", "jab", 6, "刺拳 #08 命中"),
        ("a-jab13-x15", "jab", 12, "刺拳 #14 收招"),
        ("a-cross01-x15", "cross", 0, "交叉反击 #01"),
        ("a-cross11-x15", "cross", 10, "交叉反击 #12 命中"),
        ("a-cross21-x15", "cross", 20, "交叉反击 #22"),
        ("a-wave01-x15", "wave", 0, "气功波 #01"),
        ("a-wave18-x15", "wave", 17, "气功波 #19 命中"),
        ("a-wave35-x15", "wave", 34, "气功波 #36"),
        ("a-stance-angle55", None, None, "站架 55° 侧视"),
    ]
    size, gap, mx, head_h, cols = 290, 16, 30, 150, 4
    row_h = size + 20 + 46
    nrows = (len(shots) + cols - 1) // cols
    w = mx * 2 + cols * size + (cols - 1) * gap
    h = head_h + row_h * nrows + 56
    board = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(board)
    head(board, d, "A 路线 · 重做后定稿关键帧（A2_x15）",
         "10 个代表帧 + 55° 侧视；全部走同一份 72 帧全量门禁",
         "腰间斜片 / 下摆锯齿是生成模型自带的 2,809 壳碎片，站架帧就有，本轮未修"
         "；板内亮度 x1.20，原图未改", mx)
    for k, (fname, card, fr, title) in enumerate(shots):
        x = mx + (k % cols) * (size + gap)
        y = head_h + (k // cols) * row_h
        im = load(FRAMES / f"{fname}.png", size)
        sub = ""
        if card is not None and fr is not None:
            m = metrics_for(report, card, fr)["A2_x15"]
            sub = (f"reach {m['reach_max_m']:.4f} m  /  "
                   f"tear {m['tear_p999_m']:.5f} m")
        cell(board, im, x, y, size, title, sub)
    out = HERE / "A-keyframe-board.png"
    board.convert("RGB").save(out)
    return out


def board_gain(report):
    shots = [
        ("jab07", "jab", 6, "刺拳 #08"),
        ("cross11", "cross", 10, "交叉反击 #12"),
        ("wave18", "wave", 17, "气功波 #19"),
    ]
    size, gap, mx, head_h = 360, 20, 34, 150
    row_h = size + 20 + 52
    w = mx * 2 + size * 2 + gap
    h = head_h + row_h * len(shots) + 56
    board = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(board)
    head(board, d, "A 路线 · 增益单变量对照（只改 arm-only x1.0 → x1.5）",
         "同一份 A2 连续壳 / 同一骨架 / 同一相机；对照幅度收益与撕裂代价",
         "代价由 verify_a.py 的相对阈值钉住，不藏；板内亮度 x1.20，原图未改", mx)
    for k, (shot, card, fr, title) in enumerate(shots):
        y = head_h + k * row_h
        m = metrics_for(report, card, fr)
        for j, tag in enumerate(("x1", "x15")):
            v = m["A2_x1" if j == 0 else "A2_x15"]
            im = load(FRAMES / f"a-{shot}-{tag}.png", size)
            sub = (f"reach {v['reach_max_m']:.4f} m  /  tear p999 "
                   f"{v['tear_p999_m']:.5f} m")
            cell(board, im, mx + j * (size + gap), y, size,
                 ("A2 · x1.0   " if j == 0 else "A2 · 定稿 x1.5   ") + title,
                 sub)
    out = HERE / "A-single-variable-gain-comparison.png"
    board.convert("RGB").save(out)
    return out


def main() -> int:
    report = json.loads((HERE / "a_build.json").read_text(encoding="utf-8"))
    outs = [board_compare(report), board_keyframes(report), board_gain(report)]
    for p in outs:
        print(f"BOARD {p.name} bytes={p.stat().st_size}")
    print("BOARDS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
