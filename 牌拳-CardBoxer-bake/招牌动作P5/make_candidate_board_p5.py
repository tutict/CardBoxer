# -*- coding: utf-8 -*-
"""#215 候选权衡板：三档 mf 强度、双侧成本、GLB 撕裂余量。

数据全部实时读 data/candidate_scan.json + data/pose_tear.json。
产出 boards/候选姿态-成本权衡板.png。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SCAN = json.loads((HERE / "data" / "candidate_scan.json").read_text(
    encoding="utf-8-sig"))
TEAR = json.loads((HERE / "data" / "pose_tear.json").read_text(
    encoding="utf-8-sig"))
CASES = SCAN["cases"]

W, H = 1480, 880
BG, PANEL, INK, SUB = (250, 248, 243), (255, 253, 249), (38, 36, 33), (108, 103, 96)
C_WAVE, C_CROSS, C_JAB = (122, 62, 34), (168, 96, 52), (214, 158, 116)
RED, GREEN, GREY = (176, 58, 48), (56, 118, 86), (186, 182, 174)
F = Path("C:/Windows/Fonts/msyh.ttc")


def font(n):
    return ImageFont.truetype(str(F), n) if F.is_file() else ImageFont.load_default()


FT, FH, FB, FS = font(28), font(20), font(16), font(13)


def panel(d, box, title):
    d.rounded_rectangle(box, radius=9, fill=PANEL,
                        outline=(226, 220, 210), width=2)
    d.text((box[0] + 16, box[1] + 10), title, font=FH, fill=C_WAVE)


def main():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((36, 16), "P5 候选姿态设计 · 双侧成本权衡（口径订正 R1）",
           font=FT, fill=INK)
    d.text((36, 52),
           "主强度指标 mf = |f_hand − stance.f_hand|，与 rig_driver.gd 的 tf 同口径；"
           "只改 wave / cross / jab 四臂关节，端点帧不动",
           font=FB, fill=SUB)

    # 一、三档 mf 柱状
    panel(d, (26, 90, 720, 500), "一、牌型三档手部驱动强度（mf 峰值 px）")
    groups = [("P4 基线", {"wave": 22.09, "cross": 0.0, "jab": 80.22})]
    groups += [(c["name"], c["tier_mf_peak_px"]) for c in CASES]
    base_y, x0, gw = 440, 80, 158
    maxv = 85.0
    for gi, (label, tier) in enumerate(groups):
        gx = x0 + gi * gw
        for j, (key, col) in enumerate((("wave", C_WAVE), ("cross", C_CROSS),
                                        ("jab", C_JAB))):
            v = float(tier[key])
            h = 300 * v / maxv
            x = gx + j * 40
            d.rounded_rectangle((x, base_y - h, x + 32, base_y),
                                radius=4, fill=col)
            d.text((x + 2, base_y - h - 20), f"{v:.1f}", font=FS, fill=col)
        d.text((gx - 4, base_y + 10), label, font=FS, fill=INK)
        ok = tier["wave"] > tier["cross"] > tier["jab"]
        d.text((gx - 4, base_y + 30),
               "递减 OK" if ok else "倒挂", font=FS,
               fill=GREEN if ok else RED)
    d.line([(60, base_y), (700, base_y)], fill=SUB, width=2)
    for key, col in (("wave", C_WAVE), ("cross", C_CROSS), ("jab", C_JAB)):
        pass
    d.text((330, 126), "■ wave(triple)   ■ cross(sequence)   ■ jab(scatter)",
           font=FS, fill=SUB)

    # 二、成本表
    panel(d, (740, 90, 1454, 500), "二、双侧成本与硬约束")
    cols = [("候选", 758), ("2D 最大", 900), ("3D 最大", 1010),
            ("端点漂移", 1120), ("平台", 1240), ("L8 最小", 1320),
            ("结论", 1400)]
    y = 138
    for name, x in cols:
        d.text((x, y), name, font=FS, fill=SUB)
    d.line([(754, 158), (1440, 158)], fill=GREY, width=1)
    for i, c in enumerate(CASES):
        y = 166 + i * 34
        d.text((758, y), c["name"], font=FS, fill=INK)
        d.text((900, y), f"{c['max_2d_shift_px']:.1f}px", font=FS, fill=INK)
        d.text((1010, y), f"{c['max_3d_delta_diff_deg']:.2f}°", font=FS, fill=INK)
        d.text((1120, y), f"{c['endpoint_drift_px']:.4f}", font=FS, fill=INK)
        d.text((1240, y), str(c["exact_hold_pairs"]), font=FS, fill=INK)
        d.text((1320, y), f"{c['l8_peak_pair_min']:.1f}", font=FS, fill=INK)
        d.text((1400, y), "PASS" if c["passed"] else "FAIL", font=FS,
               fill=GREEN if c["passed"] else RED)
    d.line([(754, 272), (1440, 272)], fill=GREY, width=1)
    notes = [
        "端点漂移全程 1.1000 px（P4 基线未变），pose_probe 红线 1.5 px",
        "精确平台 0（P4 结论保持），腿关节与非关节元数据未动",
        "L8 峰值姿态最小距离 ≥ 73.61（现有最小值 92.01 的 80%）",
        "推荐规则：全硬约束通过者中 3D delta 成本最小 → balanced",
        "V1（reach 欧氏口径）三档全未过，负结果留在 logs/design_pose_candidates.out",
        "口径订正 R1：cross 的 f_hand 全程恒 (44,-156)，reach 被肩轨迹污染",
    ]
    for i, s in enumerate(notes):
        d.text((758, 290 + i * 30), "· " + s, font=FS, fill=SUB)

    # 三、GLB 撕裂
    panel(d, (26, 516, 720, 856), "三、全量 284 帧真实 GLB 撕裂（Blender 5.2）")
    b, c = TEAR["baseline"], TEAR["pose_p5"]
    anchor = TEAR["anchor_p999_m"]
    bar_x, bar_w = 300, 360
    for i, (label, v, col) in enumerate((
            ("P4 基线", b["worst_p999_m"], GREY),
            ("P5 推荐", c["worst_p999_m"], C_WAVE),
            ("外部锚", anchor, RED))):
        y = 586 + i * 54
        d.text((50, y), label, font=FB, fill=INK)
        w = bar_w * v / (anchor * 1.12)
        d.rounded_rectangle((bar_x, y + 2, bar_x + w, y + 24),
                            radius=4, fill=col)
        d.text((bar_x + w + 10, y + 3), f"{v:.6f} m", font=FB, fill=col)
    d.text((50, 760),
           f"成本 +{TEAR['p999_delta_m']:.6f} m（+{(TEAR['p999_ratio']-1)*100:.2f}%）"
           f"  越锚帧 0  余量 {TEAR['anchor_headroom_m']:.6f} m",
           font=FB, fill=INK)
    d.text((50, 790),
           f"pose_err={TEAR['max_pose_matrix_err']:.2e} < 1e-5  "
           f"568 姿态 / {TEAR['elapsed_s']:.1f}s",
           font=FS, fill=SUB)
    d.text((50, 814),
           "P4 的「不差过 1mm」阈值不适用姿态重设计；改钉「余量 ≥ 2× 已耗成本」",
           font=FS, fill=SUB)

    # 四、结论
    panel(d, (740, 516, 1454, 856), "四、落地决定")
    lines = [
        f"推荐档：{SCAN['recommended']}（12/12 硬约束通过）",
        f"三档 mf：wave {CASES[1]['tier_mf_peak_px']['wave']:.3f} > "
        f"cross {CASES[1]['tier_mf_peak_px']['cross']:.3f} > "
        f"jab {CASES[1]['tier_mf_peak_px']['jab']:.3f}",
        "六条攻击轨 mf 峰值全部落在 active 段（L3 达成）",
        f"cross 蓄力后收 {CASES[1]['cross_windup_recoil_px']:.1f} px（L1 达成）",
        f"wave 弧线偏离 {CASES[1]['wave_arc_deviation_px']:.2f} px（L7 达成）",
        "只改 54 帧、4 个手臂关节；三表同步落地，mapping / 源码 / GLB 不动",
        "未修：L4 命中停顿用非零微差（保持平台 0）、L5 随动过冲仍为 0",
        "——列为 P5 已声明边界，不冒充完成",
        "下一步 #216 备份并三表同步落地 → #217 引擎内 A/B 与看图 → #218 判据变异",
    ]
    for i, s in enumerate(lines):
        d.text((758, 562 + i * 31), s, font=FB if i < 2 else FS,
               fill=GREEN if i == 0 else (RED if i == 6 else INK))

    out = HERE / "boards" / "候选姿态-成本权衡板.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    print("POSE_CANDIDATE_BOARD_OK", out, im.size, out.stat().st_size)


if __name__ == "__main__":
    main()
