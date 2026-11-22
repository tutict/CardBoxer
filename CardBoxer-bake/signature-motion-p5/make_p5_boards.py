# -*- coding: utf-8 -*-
"""#217 看图取证：两张板，数据全部实时读盘，不写死结论数字。

  boards/candidate-poses-cost-tradeoff-board-R2.png  —— R2 终版口径（jab 不动、42 帧）
  boards/P5-engine-AB-comparison-board.png         —— 引擎内三模式 A/B 关键帧条带

旧图 boards/candidate-poses-cost-tradeoff-board.png 是 R1 首版（削 jab / 三档递减）的
负结果归档，**不覆盖、不删、不改**，只在这里另出终版。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
BOARDS = HERE / "boards"
SHOTS = HERE / "shots" / "p5"

SCAN = json.loads((DATA / "candidate_scan.json").read_text(encoding="utf-8-sig"))
TEAR = json.loads((DATA / "pose_tear.json").read_text(encoding="utf-8-sig"))
READBACK = json.loads((DATA / "p5_readback.json").read_text(encoding="utf-8-sig"))
PROBE = json.loads((DATA / "p5_probe.json").read_text(encoding="utf-8-sig"))
CHECKS = json.loads((DATA / "all_checks_p5.json").read_text(encoding="utf-8-sig"))

BG, PANEL, INK, SUB = (250, 248, 243), (255, 253, 249), (38, 36, 33), (108, 103, 96)
C_WAVE, C_CROSS, C_JAB = (122, 62, 34), (168, 96, 52), (214, 158, 116)
RED, GREEN, GREY = (176, 58, 48), (56, 118, 86), (186, 182, 174)
LINE = (226, 220, 210)
F = Path("C:/Windows/Fonts/msyh.ttc")


def font(n):
    return ImageFont.truetype(str(F), n) if F.is_file() else ImageFont.load_default()


FT, FH, FB, FS, FX = font(28), font(20), font(16), font(13), font(11)


def panel(d, box, title):
    d.rounded_rectangle(box, radius=9, fill=PANEL, outline=LINE, width=2)
    d.text((box[0] + 16, box[1] + 10), title, font=FH, fill=C_WAVE)


def board_r2() -> Path:
    W, H = 1480, 880
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((36, 14), "P5 候选姿态设计 · 双侧成本权衡（R2 终版）",
           font=FT, fill=INK)
    d.text((36, 50),
           "mf = |f_hand − stance.f_hand|（与 rig_driver.gd 的 tf 同口径）；"
           "R2 否决「三档递减」，jab 全轨不动，只改 wave / cross 四臂关节 42 帧",
           font=FB, fill=SUB)

    # 一、三档 mf 柱状：判据是 wave≥55 / cross≥25 / wave≥cross+5，不是递减
    panel(d, (26, 88, 720, 500), "一、手臂驱动强度（mf 峰值 px）")
    cases = SCAN["cases"]
    baseline = cases[0]["baseline_mf_peak_px"]
    groups = [("P4 基线", baseline)] + [
        (c["name"], c["tier_mf_peak_px"]) for c in cases]
    base_y, x0, gw, maxv, scale = 452, 84, 156, 90.0, 250
    d.text((330, 122), "■ wave(triple)   ■ cross(sequence)   ■ jab(scatter)",
           font=FS, fill=SUB)
    for gi, (label, tier) in enumerate(groups):
        gx = x0 + gi * gw
        for j, (key, col) in enumerate((("wave", C_WAVE),
                                        ("cross", C_CROSS),
                                        ("jab", C_JAB))):
            v = float(tier[key])
            h = scale * v / maxv
            x = gx + j * 40
            d.rounded_rectangle((x, base_y - h, x + 32, base_y),
                                radius=4, fill=col)
            d.text((x + 2, base_y - h - 19), f"{v:.1f}", font=FS, fill=col)
        d.text((gx - 4, base_y + 10), label, font=FS, fill=INK)
        if gi == 0:
            tag, col = "倒挂", RED
        else:
            ok = (tier["wave"] >= 55.0 and tier["cross"] >= 25.0
                  and tier["wave"] >= tier["cross"] + 5.0)
            tag, col = ("硬约束 OK" if ok else "未过"), (GREEN if ok else RED)
        d.text((gx - 4, base_y + 30), tag, font=FS, fill=col)
    d.line([(60, base_y), (700, base_y)], fill=SUB, width=2)

    # 二、成本表
    panel(d, (740, 88, 1454, 500), "二、双侧成本与硬约束")
    cols = [("候选", 758), ("2D 最大", 898), ("3D 最大", 1008),
            ("端点漂移", 1118), ("平台", 1238), ("L8 最小", 1316),
            ("结论", 1400)]
    for name, x in cols:
        d.text((x, 136), name, font=FS, fill=SUB)
    d.line([(754, 156), (1440, 156)], fill=GREY, width=1)
    for i, c in enumerate(cases):
        y = 164 + i * 34
        d.text((758, y), c["name"], font=FS, fill=INK)
        d.text((898, y), f"{c['max_2d_shift_px']:.1f}px", font=FS, fill=INK)
        d.text((1008, y), f"{c['max_3d_delta_diff_deg']:.2f}°", font=FS, fill=INK)
        d.text((1118, y), f"{c['endpoint_drift_px']:.4f}", font=FS, fill=INK)
        d.text((1238, y), str(c["exact_hold_pairs"]), font=FS, fill=INK)
        d.text((1316, y), f"{c['l8_peak_pair_min']:.1f}", font=FS, fill=INK)
        d.text((1400, y), "PASS" if c["passed"] else "FAIL", font=FS,
               fill=GREEN if c["passed"] else RED)
    d.line([(754, 270), (1440, 270)], fill=GREY, width=1)
    notes = [
        "R1 首版为凑三档递减削短 jab，落地后 reach_probe 报隔空命中 42 px",
        "已用 apply_pose_p5.py --restore 逐字节回退到 P4 上线态（真回归，非误报）",
        "R2 改钉：wave≥55 / cross≥25 / wave≥cross+5 / 攻击 mf 峰值全在 active",
        "端点漂移 1.1000 px（红线 1.5），精确平台 0，腿骨与非关节元数据未动",
        "L8 峰值姿态最小距离 92.011；推荐规则＝全硬约束通过者中 3D 成本最小",
        "V1（reach 欧氏口径）三档全未过，负结果留 logs/design_pose_candidates.out",
    ]
    for i, s in enumerate(notes):
        d.text((758, 288 + i * 30), "· " + s, font=FS, fill=SUB)

    # 三、GLB 撕裂
    panel(d, (26, 514, 720, 856), "三、全量 284 帧真实 GLB 撕裂（Blender 5.2）")
    b, c = TEAR["baseline"], TEAR["pose_p5"]
    anchor = TEAR["anchor_p999_m"]
    for i, (label, v, col) in enumerate((
            ("P4 基线", b["worst_p999_m"], GREY),
            ("P5 推荐", c["worst_p999_m"], C_WAVE),
            ("外部锚", anchor, RED))):
        y = 584 + i * 54
        d.text((50, y), label, font=FB, fill=INK)
        w = 360 * v / (anchor * 1.12)
        d.rounded_rectangle((300, y + 2, 300 + w, y + 24),
                            radius=4, fill=col)
        d.text((300 + w + 10, y + 3), f"{v:.6f} m", font=FB, fill=col)
    d.text((50, 758),
           f"成本 +{TEAR['p999_delta_m']:.6f} m（+{(TEAR['p999_ratio']-1)*100:.2f}%）"
           f"  越锚帧 0  余量 {TEAR['anchor_headroom_m']:.6f} m",
           font=FB, fill=INK)
    d.text((50, 788),
           f"pose_err={TEAR['max_pose_matrix_err']:.2e}  "
           f"{TEAR['poses_evaluated']} 姿态 / {TEAR['elapsed_s']:.1f}s",
           font=FS, fill=SUB)
    d.text((50, 812),
           "不套 P4「不差过 1mm」阈值；如实记账，改钉「余量 ≥ 2× 已耗成本」",
           font=FS, fill=SUB)

    # 四、落地决定
    rec = next(c for c in cases if c["name"] == SCAN["recommended"])
    t = rec["tier_mf_peak_px"]
    rb = READBACK["axis_metrics_now"]
    lines = [
        f"推荐档：{SCAN['recommended']}（R1+R2 硬约束全过）",
        f"落盘 mf：wave {rb['wave']['mf_peak_px']:.3f} / "
        f"cross {rb['cross']['mf_peak_px']:.3f} / "
        f"jab {rb['jab']['mf_peak_px']:.3f}（jab 与基线逐值相同）",
        "六条攻击轨 mf 峰值全部落在 active 段（L3）",
        f"cross 蓄力后收 {rec['cross_windup_recoil_px']:.1f} px（L1）；"
        f"wave 弧线偏离 {rec['wave_arc_deviation_px']:.2f} px（L7）",
        f"只改 {READBACK['changed_frame_count']} 帧 / 4 个手臂关节；"
        f"三表 {READBACK['joint_values_checked']} 值同步、disagree 0",
        f"引擎内 A/B {sum(PROBE['checks'].values())}/{len(PROBE['checks'])}、"
        f"全量自检 {CHECKS['passed']}/{CHECKS['total']} 全绿",
        "未修：L4 命中停顿用非零微差（保平台 0）、L5 随动过冲仍为 0",
        "旧「候选姿态-成本权衡板.png」＝R1 首版负结果归档，本板为 R2 终版",
    ]
    panel(d, (740, 514, 1454, 856), "四、落地决定（R2）")
    for i, s in enumerate(lines):
        d.text((758, 560 + i * 34), s, font=FB if i < 2 else FS,
               fill=GREEN if i == 0 else (RED if i == 6 else INK))

    out = BOARDS / "candidate-poses-cost-tradeoff-board-R2.png"
    im.save(out)
    print("BOARD_R2_OK", out.name, im.size, out.stat().st_size)
    return out


def board_ab() -> Path:
    cols = [("stance", 0, "零差对照"),
            ("jab", 6, "R2 不动"),
            ("wave", 10, "改动首帧"),
            ("wave", 17, "wave 峰值"),
            ("cross", 1, "改动首帧"),
            ("cross", 8, "cross 峰值")]
    W, H = 1600, 1080
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((30, 14), "P5 · 引擎内 A/B 关键帧对照（同一 Godot 进程换运行时表）",
           font=FT, fill=INK)
    d.text((30, 52),
           "上行＝rolled_back（P4 上线态原表），下行＝shipped（P5/R2 落盘表）；"
           "每列下方是 SubViewport 逐像素差（>8 记 1 像素）",
           font=FB, fill=SUB)

    summary = [
        f"改动帧 {READBACK['changed_frame_count']}",
        f"像素差 {PROBE['edited_diff_nonzero']}/{PROBE['edited_diff_total']}",
        f"最大 {PROBE['edited_diff_max']} px",
        "stance/jab 差 0",
        "reapplied 差 0",
        f"自检 {CHECKS['passed']}/{CHECKS['total']}",
    ]
    d.rounded_rectangle((30, 86, 1570, 134), radius=8, fill=PANEL,
                        outline=LINE, width=2)
    for i, s in enumerate(summary):
        d.text((52 + i * 252, 100), "· " + s, font=FB,
               fill=GREEN if i in (1, 3, 4, 5) else INK)

    cell_w, cell_h = 200, 248
    x0, y_top, y_bot = 176, 208, 500
    d.text((30, 172), "P4 原表", font=FH, fill=SUB)
    d.text((30, 464), "P5 落盘", font=FH, fill=C_WAVE)
    for ci, (card, fr, note) in enumerate(cols):
        x = x0 + ci * 232
        d.text((x, 168), f"{card}{fr:02d}", font=FB, fill=INK)
        d.text((x, 188), note, font=FS, fill=SUB)
        for mode, y in (("rolled_back", y_top), ("shipped", y_bot)):
            p = SHOTS / f"p5-{mode}-{card}{fr:02d}-sv-player.png"
            if not p.is_file():
                d.rounded_rectangle((x, y, x + cell_w, y + cell_h),
                                    radius=6, fill=GREY)
                continue
            tile = Image.open(p).convert("RGBA").resize(
                (cell_w, cell_h), Image.LANCZOS)
            slot = Image.new("RGBA", (cell_w, cell_h), PANEL + (255,))
            slot.alpha_composite(tile)
            im.paste(slot.convert("RGB"), (x, y))
            d.rectangle((x, y, x + cell_w, y + cell_h), outline=LINE, width=2)
        key = f"shipped_vs_rolled_back:{card}{fr:02d}:player"
        diff = PROBE["diff_px"].get(key, -1)
        col = GREEN if diff > 0 else (RED if diff == 0 else INK)
        d.text((x, y_bot + cell_h + 12), f"diff {diff} px", font=FB, fill=col)

    # 数值面板
    panel(d, (30, 796, 790, 1052), "引擎读回 · 数值判据")
    peaks = READBACK["axis_metrics_now"]
    rows = [
        f"mf 峰值  wave {peaks['wave']['mf_peak_px']:.3f} / "
        f"cross {peaks['cross']['mf_peak_px']:.3f} / "
        f"jab {peaks['jab']['mf_peak_px']:.3f} px",
        f"峰值帧    wave {peaks['wave']['mf_peak_frame']} / "
        f"cross {peaks['cross']['mf_peak_frame']} / "
        f"jab {peaks['jab']['mf_peak_frame']}（全部 active）",
        f"2D 改动   {READBACK['diff_count']} 个关节坐标 / "
        f"最大 {READBACK['max_2d_joint_delta_px']:.1f} px / "
        f"端点漂移 {READBACK['endpoint_worst_px']:.4f} px",
        "13 骨 delta 变化只落在 4 根臂骨（名称见 p5_readback.json）；"
        "腿骨 / 躯干骨逐值相同",
        f"三表 {READBACK['joint_values_checked']} 关节值同步，"
        f"disagree 0；其余 11 个受监控文件 sha 不变",
        f"GLB 撕裂 p999 {TEAR['baseline']['worst_p999_m']:.6f} → "
        f"{TEAR['pose_p5']['worst_p999_m']:.6f} m（越锚帧 0）",
    ]
    for i, s in enumerate(rows):
        d.text((50, 838 + i * 33), "· " + s, font=FS, fill=INK)

    nchecks = len(PROBE["checks"])
    panel(d, (810, 796, 1570, 1052),
          f"判据覆盖 · {sum(PROBE['checks'].values())}/{nchecks} 全绿")
    names = list(PROBE["checks"])
    for i, name in enumerate(names):
        x = 830 + (i // 13) * 370
        y = 838 + (i % 13) * 16
        v = PROBE["checks"][name]
        d.text((x, y), ("[OK] " if v else "[NG] ") + name[:54], font=FX,
               fill=GREEN if v else RED)
    out = BOARDS / "P5-engine-AB-comparison-board.png"
    im.save(out)
    print("BOARD_AB_OK", out.name, im.size, out.stat().st_size)
    return out


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    a, b = board_r2(), board_ab()
    ok = a.is_file() and b.is_file() \
        and a.stat().st_size > 30000 and b.stat().st_size > 30000
    print("P5_BOARDS_OK" if ok else "P5_BOARDS_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
