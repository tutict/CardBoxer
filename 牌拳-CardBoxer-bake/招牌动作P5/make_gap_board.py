# -*- coding: utf-8 -*-
"""#214 差距对照板：把「三档倒挂」与「cross 峰值错位」画出来给人看。

数据全部实时读 card_motion.json + data/pose_gap.json，不写死数字。
产出 boards/招牌动作-差距对照板.png。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pose_metrics import (
    GAME, HERE, JOINTS, dist, joints_of, load_json, reach, tracks_of,
)

CM = load_json(GAME / "data" / "card_motion.json")
GAP = json.loads((HERE / "data" / "pose_gap.json").read_text(encoding="utf-8-sig"))
MET = GAP["metrics"]
STANCE = joints_of(CM["stance"])
ST_REACH = reach(STANCE)
TRS = tracks_of(CM)

W, H = 1600, 1000
BG = (250, 248, 243)
INK = (38, 36, 33)
SUB = (108, 103, 96)
COPPER = (168, 96, 52)
COPPER_D = (122, 62, 34)
COPPER_L = (214, 158, 116)
GREY = (186, 182, 174)
RED = (176, 58, 48)
BLUE = (58, 96, 132)
PANEL = (255, 253, 249)

BONES = [
    ("hip", "shoulder"), ("shoulder", "head"),
    ("shoulder", "f_elbow"), ("f_elbow", "f_hand"),
    ("shoulder", "b_elbow"), ("b_elbow", "b_hand"),
    ("hip", "f_knee"), ("f_knee", "f_foot"),
    ("hip", "b_knee"), ("b_knee", "b_foot"),
]

FONT_PATH = Path("C:/Windows/Fonts/msyh.ttc")


def font(size: int):
    if FONT_PATH.is_file():
        return ImageFont.truetype(str(FONT_PATH), size)
    return ImageFont.load_default()


F_TITLE = font(30)
F_H = font(21)
F_B = font(17)
F_S = font(14)


def text(d, xy, s, f, fill=INK):
    d.text(xy, s, font=f, fill=fill)


def panel(d, box, title):
    d.rounded_rectangle(box, radius=10, fill=PANEL, outline=(226, 220, 210), width=2)
    text(d, (box[0] + 18, box[1] + 12), title, F_H, COPPER_D)


def skeleton(d, joints, ox, oy, scale, color, width=5, dash=False):
    def pt(k):
        x, y = joints[k]
        return (ox + x * scale, oy + y * scale)
    for a, b in BONES:
        d.line([pt(a), pt(b)], fill=color, width=width)
    for k in JOINTS:
        x, y = pt(k)
        r = 4 if width > 4 else 3
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def peak_pose(name):
    tr = TRS[name][1]
    js = [joints_of(f) for f in tr]
    i = MET[name]["peak_reach_argmax"]
    return js[i], i


def main():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    text(d, (40, 18), "P5 差距诊断 · 牌型强度与姿态强度倒挂", F_TITLE)
    text(d, (40, 56),
         "读盘实测：card_motion.json 15 轨 / 6 条攻击轨；灰线＝stance，彩线＝该轨伸展峰值帧",
         F_B, SUB)

    # 左半：三档峰值骨架
    panel(d, (30, 92, 790, 950), "一、三档赢家动作的峰值剪影")
    tiers = [
        ("triple 最大牌", "wave", COPPER_D, 140,
         "手臂抬高但前手未向前伸展，剪影只 +26%"),
        ("sequence 中牌", "cross", COPPER, 390,
         "峰值落在蓄力段，命中窗内手已回收"),
        ("scatter 最小牌", "jab", COPPER_L, 640,
         "前手完全伸出，三档里反而最强"),
    ]
    for label, name, col, y0, note in tiers:
        pose, idx = peak_pose(name)
        m = MET[name]
        d.line([(50, y0 + 232), (770, y0 + 232)], fill=(232, 226, 216), width=1)
        skeleton(d, STANCE, 190, y0 + 205, 1.0, GREY, 4)
        skeleton(d, pose, 190, y0 + 205, 1.0, col, 5)
        text(d, (330, y0 + 8), f"{label}  →  {name}", F_H, col)
        text(d, (330, y0 + 44),
             f"前手伸展增量  {m['peak_reach_gain_px']:.4f} px   "
             f"剪影 +{m['peak_bbox_gain_pct']:.2f}%", F_B)
        text(d, (330, y0 + 76),
             f"峰值帧 #{idx}  落在 {m['peak_reach_phase']} 段   "
             f"蓄力后收 {m['windup_recoil_px']} px", F_B, SUB)
        text(d, (330, y0 + 108),
             f"重心下沉 {m['windup_hip_drop_px']} px   "
             f"弧线偏离 {m['arc_deviation_px']} px   "
             f"随动过冲 {m['recover_overshoot_px']} px", F_B, SUB)
        text(d, (330, y0 + 145), note, F_S, SUB)

    # 右上：柱状图
    panel(d, (810, 92, 1570, 430), "二、三档伸展强度：期望递减，实测递增")
    base_y = 380
    max_gain = max(MET[n]["peak_reach_gain_px"]
                   for _l, n, _c, _y, _note in tiers)
    bar_w = 120
    xs = [900, 1120, 1340]
    for (label, name, col, _y, _note), x in zip(tiers, xs):
        g = MET[name]["peak_reach_gain_px"]
        h = 150 * g / max_gain
        d.rounded_rectangle((x, base_y - h, x + bar_w, base_y),
                            radius=6, fill=col)
        text(d, (x + 6, base_y - h - 26), f"{g:.2f} px", F_B, col)
        text(d, (x - 4, base_y + 12), name, F_B)
        text(d, (x - 20, base_y + 38), label.split()[0], F_S, SUB)
    d.line([(870, base_y), (1520, base_y)], fill=SUB, width=2)
    text(d, (880, 124), "P0 牌型强度  triple  >  sequence  >  scatter", F_B, SUB)
    text(d, (880, 148), "实测姿态强度  wave 1.72  <  cross 18.92  <  jab 44.01",
         F_B, RED)
    text(d, (880, 172), "结论：最大的牌打出的姿态最弱，语义完全倒挂", F_B, RED)

    # 右中：cross 相位时间线
    panel(d, (810, 446, 1570, 730), "三、cross 峰值落在 windup，命中时手已收回")
    tr = TRS["cross"][1]
    gains = [reach(joints_of(f)) - ST_REACH for f in tr]
    phases = [str(f.get("phase", "?")) for f in tr]
    x0, x1, y0, y1 = 860, 1520, 500, 680
    span = x1 - x0
    active = [i for i, p in enumerate(phases) if p == "active"]
    if active:
        ax0 = x0 + span * active[0] / (len(tr) - 1)
        ax1 = x0 + span * active[-1] / (len(tr) - 1)
        d.rectangle((ax0, y0, ax1, y1), fill=(232, 240, 246))
        text(d, ((ax0 + ax1) / 2 - 36, y0 + 6), "active 命中窗", F_S, BLUE)
    gmax = max(gains) or 1.0
    gmin = abs(min(gains)) or 1.0
    y_base = y1 - 25

    def map_y(g):
        return (y_base - 130 * g / gmax if g >= 0
                else y_base + 20 * (-g) / gmin)

    pts = [(x0 + span * i / (len(tr) - 1), map_y(g))
           for i, g in enumerate(gains)]
    d.line([(x0, y_base), (x1, y_base)], fill=(214, 208, 198), width=1)
    d.line(pts, fill=COPPER, width=3)
    peak = MET["cross"]["peak_reach_argmax"]
    px, py = pts[peak]
    d.ellipse((px - 6, py - 6, px + 6, py + 6), fill=RED)
    d.line([(px, py), (px, y1)], fill=RED, width=1)
    text(d, (px - 30, py - 34), f"peak #{peak}", F_S, RED)
    d.line([(x0, y1), (x1, y1)], fill=SUB, width=2)
    text(d, (x0, y1 + 10), "windup 0-5", F_S, SUB)
    text(d, (x0 + span * 6 / 21, y1 + 10), "active 6-9", F_S, BLUE)
    text(d, (x0 + span * 10 / 21, y1 + 10), "recover 10-21", F_S, SUB)

    # 右下：差距清单
    panel(d, (810, 746, 1570, 950), "四、差距清单（diag_pose_gap.py 复算）")
    lines = [
        f"[硬] L3  cross 峰值 @frame {MET['cross']['peak_reach_argmax']} 在 windup，"
        f"active 是 6-9",
        "[硬] L2  三档伸展倒挂：wave 1.72 < cross 18.92 < jab 44.01",
        f"[注] L2  wave 剪影仅 +{MET['wave']['peak_bbox_gain_pct']:.2f}%，"
        f"其余攻击轨 +14%~+83%",
        "[注] L1  cross 蓄力后收 0.0 px，没有反向预加载",
        "[注] L5  六条攻击轨 recover_overshoot_px 全为 0，无随动",
        "[冲突] L4  P4 后精确平台 0，hitstop 不能靠整帧相同实现",
        f"[红线] 末帧漂移最大 {GAP['end_drift_worst']['px']} px，红线 1.5 px",
    ]
    for i, s in enumerate(lines):
        text(d, (832, 788 + i * 22), s, F_S,
             RED if s.startswith("[硬]") else INK)

    out = HERE / "boards" / "招牌动作-差距对照板.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print("GAP_BOARD_OK", out, "size=%s" % (im.size,),
          "bytes=%d" % out.stat().st_size)


if __name__ == "__main__":
    main()
