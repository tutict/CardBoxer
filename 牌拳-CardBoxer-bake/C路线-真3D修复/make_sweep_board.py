"""增益 sweep 的姿态对照板：把「能不能放大」这个定性判断钉成一张可看的图。

选 cross#12 同一帧，因为它在看图里对增益最敏感（后手抬臂 + 躯干侧倾）。
上排 all（躯干/腿/臂一起放大），下排 arm_only（只放大臂）。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"
OUT = HERE / "增益-姿态对照板.png"
STATS = HERE / "gain_sweep.json"

CELL, MARGIN, HEAD, LABEL = 320, 20, 112, 30
BG, PANEL = (24, 27, 38), (36, 41, 56)


def font(size, bold=False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc") if bold \
        else (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf")
    for p in names:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


ROWS = [
    ("all · 躯干/腿/臂一起放大", [
        ("sweep-g1.0-cross11.png", "x1.0 基线 · 直立、幅度小"),
        ("sweep-g1.5-cross11.png", "x1.5 推荐 · 直立、幅度可读"),
        ("sweep-g2.0-cross11.png", "x2.0 勉强 · 开始侧倾"),
        ("sweep-g3.0-cross11.png", "x3.0 不可用 · 斜转、手臂出框"),
    ]),
    ("arm_only · 只放大手臂增益", [
        ("sweep-arm-g1.5-cross11.png", "x1.5 · 直立、手臂放大"),
        ("sweep-arm-g2.0-cross11.png", "x2.0 · 直立、抬臂更高"),
        ("sweep-arm-g3.0-cross11.png", "x3.0 不可用 · 手臂抬出画面"),
        ("c-jab-rigid.png", "对照：旧刚性权重（撕裂扇形）"),
    ]),
]


def main() -> int:
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    verdict = stats["verdict"]
    W = MARGIN * 2 + 4 * CELL
    H = HEAD + 2 * (LABEL + CELL + 34) + 44
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    FH, FL, FS = font(24, True), font(17, True), font(14)
    d.text((MARGIN, 14), "C 路线 · 增益扫描姿态对照（同一 cross#12 帧）",
           font=FH, fill=(238, 242, 252))
    d.text((MARGIN, 48),
           f"撕裂最坏 p999 = {verdict['worst_sweep_p999_m']:.5f} m，"
           f"是刚性基线 {verdict['rigid_baseline_p999_m']} m 的 "
           f"{verdict['worst_over_rigid']*100:.1f}% —— 拓扑修复在所有档都成立",
           font=FS, fill=(160, 170, 190))

    for r, (title, items) in enumerate(ROWS):
        top = HEAD + r * (LABEL + CELL + 34)
        d.text((MARGIN, top - 28), title, font=FL, fill=(240, 214, 160))
        for c, (fn, label) in enumerate(items):
            p = FRAMES / fn
            assert p.is_file(), f"missing {p}"
            x = MARGIN + c * CELL
            d.rectangle((x, top, x + CELL - 8, top + CELL), fill=PANEL)
            cell = Image.open(p).convert("RGBA").resize(
                (CELL - 8, CELL), Image.LANCZOS)
            im.paste(cell, (x, top), cell)
            d.text((x + 8, top + CELL + 8), label, font=FS, fill=(206, 214, 230))
    d.text((MARGIN, H - 26),
           "可用区间 x1.0–x1.5（x2.0 勉强）；幅度受 retarget 增益限制，不是拓扑问题。"
           "要放大只调 arm_gain_deg，绝不调 torso_gain/torso_cap。",
           font=FS, fill=(190, 198, 214))
    im.save(OUT)
    print(f"SWEEP_BOARD_OK size={im.size} bytes={OUT.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
