"""P4 · 候选改法权衡板（纯读盘 + 合成，不改游戏）。

上板：精确平台 / 可辨平台双柱，现状 255 / 308 作红虚线参照。
下板：2D 侧最大关节位移（px），把「几乎不动」与「改动作」摆在一起看。
用法：python make_candidate_board.py
产出：boards/P4-candidate-tradeoffs.png
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SCAN = HERE / "data" / "candidate_scan.json"
OUT = HERE / "boards" / "P4-candidate-tradeoffs.png"

BG = (22, 22, 28)
FG = (230, 234, 242)
MUTED = (180, 190, 206)
GREY = (140, 150, 168)
ORANGE = (255, 186, 92)
GREEN = (110, 190, 150)
RED = (214, 108, 108)
BLUE = (116, 166, 224)

SHOW = [
    ("现状", "micro_0"),
    ("微扰0.2", "micro_0.2"),
    ("微扰0.5", "micro_0.5"),
    ("微扰1.0", "micro_1"),
    ("微扰2.0", "micro_2"),
    ("过渡LERP", "lerp_transition"),
    ("混合(推荐)", "hybrid_lerp_micro03"),
]


def font(sz: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                pass
    return ImageFont.load_default()


def draw_panel(d, x0, x1, top, bot, title, vmax, unit,
               series, f15, f13, f12):
    d.text((x0, top - 32), title, font=f15, fill=FG)
    d.line((x0, bot, x1, bot), fill=(110, 114, 128), width=2)
    for tick in range(0, vmax + 1, max(1, vmax // 4)):
        y = bot - (bot - top) * tick / vmax
        d.line((x0, y, x1, y), fill=(52, 56, 66), width=1)
        d.text((x0 - 46, y - 9), f"{tick}{unit}", font=f12, fill=MUTED)
    n = len(series)
    slot = (x1 - x0) / n
    bw = min(30, slot / 3.2)
    for i, (label, values) in enumerate(series):
        cx = x0 + slot * (i + 0.5)
        for j, (v, color) in enumerate(values):
            bx = cx + (j - (len(values) - 1) / 2) * (bw + 4)
            h = max(3.0, (bot - top) * min(v, vmax) / vmax)
            d.rectangle((bx - bw / 2, bot - h, bx + bw / 2, bot),
                        fill=color)
            # 高柱数值画柱内顶端（避免压字），矮柱画柱上方（避免压底轴）
            txt = (f"{v:.2f}".rstrip("0").rstrip(".") if v < 10
                   else str(int(round(v))))
            if h >= 22:
                d.text((bx - 14, bot - h + 4), txt, font=f12, fill=BG)
            else:
                d.text((bx - 14, bot - h - 17), txt, font=f12, fill=FG)
        d.text((cx - 34, bot + 8), label, font=f12, fill=FG)


def main() -> int:
    rep = json.loads(SCAN.read_text(encoding="utf-8"))
    rows = rep["rows"]
    W, H = 1400, 830
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f26, f15, f13, f12 = font(26), font(15), font(13), font(12)
    d.text((20, 10), "P4 · 数据层原生平台：候选改法权衡",
           font=f26, fill=FG)
    d.text((20, 48),
           "灰 = 精确平台（相邻输出差 < 1e-6°），橙 = 可辨平台（< 0.1°）；"
           "蓝 = 2D 侧最大关节位移",
           font=f15, fill=MUTED)
    d.text((20, 76),
           "红线是现状 255 / 308。精确平台归零不难，难的是可辨平台真的下降",
           font=f13, fill=RED)

    left, right = 110, 1340
    pairs = [(lab, rows[k]["exact_flat_pairs"],
              rows[k]["perceptual_flat_pairs"],
              rows[k]["max_joint_delta_px"]) for lab, k in SHOW]

    top, bot = 140, 400
    draw_panel(d, left, right, top, bot,
               "平台对数（15 轨 × 284 帧 × 4 腿骨 = 1076 骨帧对）",
               320, "", [(lab, [(a, GREY), (b, ORANGE)])
                         for lab, a, b, _ in pairs],
               f15, f13, f12)
    for val, txt in ((255, "现状精确 255"), (308, "现状可辨 308")):
        y = bot - (bot - top) * val / 320
        d.line((left, y, right, y), fill=RED, width=1)
    d.text((right - 250, top - 30), "现状精确 255 / 可辨 308",
           font=f13, fill=RED)

    top2, bot2 = 500, 700
    draw_panel(d, left, right, top2, bot2,
               "2D 侧最大关节位移（px，人物高约 200 px）",
               36, "", [(lab, [(round(px, 2), BLUE)])
                        for lab, _, _, px in pairs],
               f15, f13, f12)
    d.text((right - 330, top2 - 30), "柱内数字为位移（px，保留 2 位）",
           font=f13, fill=MUTED)

    best = rep["recommended_case"]
    d.text((20, 734),
           f"推荐 {best}：精确平台 0，可辨平台 "
           f"{rows[best]['perceptual_flat_pairs']}"
           f"（现状 308），最大关节位移 "
           f"{rows[best]['max_joint_delta_px']} px。",
           font=f15, fill=GREEN)
    d.text((20, 762),
           "代价说清楚：混合档把「定格蓄力」改成平滑过渡，2D 动作会变；"
           "微扰档几乎不动 2D，但可辨平台只小幅下降。",
           font=f15, fill=FG)
    d.text((20, 792),
           "真实 GLB 全量 284 帧撕裂成本另见 P4-全量撕裂权衡板；"
           "看图复核在引擎内 A/B 阶段。",
           font=f13, fill=MUTED)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    im.save(OUT)
    print("BOARD", str(OUT), im.size, "BYTES", OUT.stat().st_size)
    print("RECOMMENDED", best)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
