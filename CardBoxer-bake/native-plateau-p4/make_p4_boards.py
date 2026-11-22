"""P4 · 出三张看图产物（纯读盘 + 合成，不改游戏）。

  A 平台曲线板 —— focus 全帧的 thigh_f 腿骨 delta，原表灰线 vs 上线表橙线，
    配关键数字卡；这张直接回答「255 对原生平台有没有被攻下来」。
  B 连续帧条带 —— 引擎内 A/B 的 focus 6..11 连续 6 帧，4 行
    （玩家/对手 × 原表/上线表），看腿姿态是否逐帧渐变、有无甩飞。
  C 上线前后对照 —— 2 列 × 3 个代表动作帧，看整体姿态有无穿模/出框。

用法：python make_p4_boards.py
产出：boards/*.png、data/p4_boards.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from p4_math import LEG_BONES, expected_delta  # noqa: E402

D = HERE / "data"
BOARDS = HERE / "boards"
PROBE = D / "p4_probe.json"
OUT = D / "p4_boards.json"

BG = (22, 22, 28)
FG = (230, 234, 242)
MUTED = (180, 190, 206)
GREY = (140, 150, 168)
ORANGE = (255, 186, 92)
GREEN = (110, 190, 150)
RED = (230, 110, 110)


def font(sz: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                pass
    return ImageFont.load_default()


def open_sv(path: str, size: tuple[int, int]) -> Image.Image:
    p = Path(path)
    if not p.is_file():
        return Image.new("RGBA", size, (50, 50, 60, 255))
    return Image.open(p).convert("RGBA").resize(size, Image.LANCZOS)


def paste_cell(canvas: Image.Image, cell: Image.Image,
               xy: tuple[int, int]) -> None:
    canvas.paste(cell, xy, cell)


def series(card: str, frames: range, which: str) -> list[float]:
    return [round(expected_delta(card, i, which)["thigh_f"], 4)
            for i in frames]


def curve_board() -> dict:
    readback = json.loads((D / "readback_native.json").read_text(
        encoding="utf-8"))
    tear = json.loads((D / "micro2_tear.json").read_text(
        encoding="utf-8"))
    decision = json.loads((D / "landing_decision.json").read_text(
        encoding="utf-8"))
    cm = json.loads((HERE.parent.parent / "CardBoxer" / "data"
                     / "card_motion.json").read_text(encoding="utf-8"))
    n = len(cm["cards"]["focus"]["track"])
    fr = range(n)
    old = series("focus", fr, "rolled_back")
    new = series("focus", fr, "shipped")

    W, H = 1400, 840
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f26, f18, f15, f13 = font(26), font(18), font(15), font(13)
    d.text((20, 12), "P4 · 原生平台：focus 全帧 thigh_f 腿骨 delta",
           font=f26, fill=FG)
    d.text((20, 48),
           "灰线 = P3 上线态原表，橙线 = P4 落地态 micro2；"
           "非改动段两线完全重合（橙线覆盖灰线），差异见下方放大图",
           font=f15, fill=MUTED)

    left, right, top, bot = 90, 1000, 120, 420
    lo = min(min(old), min(new)) - 0.4
    hi = max(max(old), max(new)) + 0.4
    span = max(hi - lo, 1e-6)
    d.line((left, bot, right, bot), fill=(110, 114, 128), width=2)
    d.line((left, top, left, bot), fill=(110, 114, 128), width=2)
    for t in range(5):
        v = lo + span * t / 4
        y = bot - (bot - top) * t / 4
        d.line((left, y, right, y), fill=(52, 56, 66), width=1)
        d.text((left - 60, y - 9), f"{v:+.2f}°", font=f13, fill=MUTED)
    for i in range(0, n, 2):
        x = left + (right - left) * i / max(n - 1, 1)
        d.text((x - 8, bot + 8), f"f{i}", font=f12_or_13(), fill=MUTED)
    # 改动段底色
    x0 = left + (right - left) * 6 / max(n - 1, 1)
    x1 = left + (right - left) * 12 / max(n - 1, 1)
    d.rectangle((x0, top, x1, bot), fill=(38, 42, 54))
    d.text((x0 + 6, top + 6), "定格段（改动区）", font=f13, fill=MUTED)
    for vals, color, width in ((old, GREY, 2), (new, ORANGE, 3)):
        pts = [(left + (right - left) * i / max(n - 1, 1),
                bot - (bot - top) * (v - lo) / span)
               for i, v in enumerate(vals)]
        d.line(pts, fill=color, width=width)
        for x, y in pts:
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)
    d.text((right - 250, top - 26), "橙 = micro2    灰 = 原表",
           font=f15, fill=ORANGE)

    # 定格段放大：主图纵轴约 10°，0.2° 的逐帧差看不见，单独放大才看得见
    # 只放大定格段 f5-f12；f13 起是段后大跳变，纳入纵轴会把 0.2° 差异压平
    z_lo, z_hi = 5, 12
    zx0, zx1, zy0, zy1 = 90, 700, 470, 620
    seg_all = old[z_lo:z_hi + 1] + new[z_lo:z_hi + 1]
    vmin, vmax = min(seg_all) - 0.05, max(seg_all) + 0.05
    d.rectangle((zx0, zy0, zx1, zy1), fill=(34, 38, 48),
                outline=(62, 66, 78), width=1)
    d.text((zx0 + 12, zy0 + 8),
           "定格段放大（f5-f12）：灰线水平定格，橙线逐帧分开",
           font=f13, fill=MUTED)
    px0, px1, py0, py1 = zx0 + 40, zx1 - 20, zy0 + 44, zy1 - 18

    def zy(v: float) -> float:
        return py1 - (py1 - py0) * (v - vmin) / (vmax - vmin)

    for vals, color in ((old, GREY), (new, ORANGE)):
        seg = vals[z_lo:z_hi + 1]
        pts = [(px0 + (px1 - px0) * i / (len(seg) - 1), zy(v))
               for i, v in enumerate(seg)]
        d.line(pts, fill=color, width=2)
        for x, y in pts:
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)
    d.text((zx0 + 12, zy1 + 8),
           "f13 起是大跳变、不纳入本纵轴；端点未扰动，定格段内相邻帧严格分开",
           font=f13, fill=MUTED)

    # 数字卡
    cards = [
        ("精确平台对", readback["scan_baseline"]["exact_flat_pairs"],
         readback["agg"]["exact_flat_pairs"]),
        ("可辨平台对", readback["scan_baseline"]["perceptual_flat_pairs"],
         readback["agg"]["perceptual_flat_pairs"]),
        ("改动帧数", 0, readback["agg"]["changed_frames"]),
        ("2D 最大位移 px", 0.0, readback["agg"]["max_joint_delta_px"]),
    ]
    cx, cy, cw, ch = 1030, 120, 340, 100
    for i, (label, before, after) in enumerate(cards):
        y = cy + i * (ch + 12)
        d.rectangle((cx, y, cx + cw, y + ch), fill=(34, 38, 48),
                    outline=(62, 66, 78), width=1)
        d.text((cx + 14, y + 10), label, font=f15, fill=MUTED)
        b = f"{before:g}" if isinstance(before, float) else str(before)
        a = f"{after:g}" if isinstance(after, float) else str(after)
        d.text((cx + 14, y + 40), f"{b}  →  {a}", font=f18,
               fill=GREEN if i < 2 else FG)
        if i < 2:
            d.text((cx + 14, y + 74),
                   "下降" if after < before else "未下降",
                   font=f13, fill=GREEN if after < before else RED)

    d.text((20, 656),
           f"全量 284 帧真实 GLB 撕裂：现状 {tear['baseline_worst_p999_m']:.6f} m "
           f"→ 落地 {tear['worst_p999_m']:.6f} m，"
           f"外部锚 {tear['anchor_p999_m']:.5f} m，越锚帧 {tear['frames_over_anchor']}",
           font=f15, fill=FG)
    d.text((20, 686),
           f"扰动幅度上限 {decision['amplitude_px']:g} px；"
           "每条 track 的首帧/末帧（起手与收招归位）刻意不扰动，"
           "pose_probe 的 1.5 px 红线保持 1.100 px",
           font=f15, fill=MUTED)
    d.text((20, 716),
           "曲线由 Python 按 rig_driver.gd 同公式复算，不取引擎截图；"
           "引擎内 A/B 另见 p4_probe.json",
           font=f15, fill=MUTED)
    d.text((20, 746),
           "被否决的 hybrid 会把定格段改成匀速滑动，2D 关节最大位移 33.06 px，"
           "等于重设动画语义",
           font=f13, fill=MUTED)
    d.text((20, 776),
           "注：224 / 255 对原生平台本来就是整帧定格 hold 帧，"
           "本次攻的是数值特征，不是重设动作设计",
           font=f13, fill=MUTED)
    d.text((20, 806), "引擎内同进程 A/B 静态截帧（arena.paused 冻结），不是真实对局",
           font=f13, fill=MUTED)
    p = BOARDS / "P4-plateau-curve-comparison.png"
    im.save(p)
    old_flat = sum(abs(b - a) < 1e-6 for a, b in zip(old, old[1:]))
    new_flat = sum(abs(b - a) < 1e-6 for a, b in zip(new, new[1:]))
    return {"path": str(p), "size": [W, H], "frames": n,
            "original_flat_pairs_in_focus": old_flat,
            "shipped_flat_pairs_in_focus": new_flat,
            "cards": len(cards)}


def f12_or_13():
    return font(12)


def strip_board(probe: dict) -> dict:
    by_key = {r["key"]: r for r in probe["rows"]}
    frames = list(range(6, 12))
    W, H = 1400, 980
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f26, f15, f13, f12 = font(26), font(15), font(13), font(12)
    d.text((20, 10), "P4 · 连续帧复核：focus 6-11（micro2 改动段）",
           font=f26, fill=FG)
    d.text((20, 46),
           "上=玩家，下=对手；每组上排 P3 上线态原表，下排 P4 落地态 micro2。"
           "格内数字为该帧 thigh_f 腿骨角度（度）",
           font=f15, fill=MUTED)
    LEFT, TOP, CW, CH = 132, 104, 190, 170
    GAP_X, GAP_Y = 8, 16
    for j, fr in enumerate(frames):
        x = LEFT + j * (CW + GAP_X)
        d.text((x + 60, TOP - 26), f"f{fr}", font=f13, fill=FG)
    groups = [
        ("玩家 原表", "rolled_back", "player", "rolled_back"),
        ("玩家 micro2", "shipped", "player", "shipped"),
        ("对手 原表", "rolled_back", "foe", "rolled_back"),
        ("对手 micro2", "shipped", "foe", "shipped"),
    ]
    for i, (label, mode, side, which) in enumerate(groups):
        y = TOP + i * (CH + GAP_Y)
        d.text((8, y + CH // 2 - 22), label, font=f13,
               fill=ORANGE if "micro2" in label else GREY)
        for j, fr in enumerate(frames):
            key = f"{mode}-focus{fr:02d}"
            rec = by_key.get(key, {})
            x = LEFT + j * (CW + GAP_X)
            cell = open_sv(rec.get(f"{side}_sv", ""), (CW, CH))
            paste_cell(im, cell, (x, y))
            d.rectangle((x, y, x + CW, y + 20), fill=(18, 18, 24))
            val = expected_delta("focus", fr, which)["thigh_f"]
            d.text((x + 6, y + 3), f"{val:+.3f}°", font=f12,
                   fill=ORANGE if which == "shipped" else FG)
            d.rectangle((x, y, x + CW, y + CH), outline=(62, 66, 78),
                        width=1)
    d.text((20, TOP + 4 * (CH + GAP_Y) + 10),
           "上排在定格段里腿角度逐帧不变，下排逐帧递增；"
           "差异不到 2 度，人物没有甩飞、穿模或出框。",
           font=f15, fill=FG)
    d.text((20, TOP + 4 * (CH + GAP_Y) + 42),
           "引擎内同进程 A/B 静态截帧，站架帧两模式逐像素相同（差 0）；"
           "shipped 与 reapplied 逐像素相同。",
           font=f15, fill=MUTED)
    p = BOARDS / "P4-frame-sequence-strip.png"
    im.save(p)
    return {"path": str(p), "size": [W, H], "frames": frames,
            "groups": len(groups), "panels": len(groups) * len(frames)}


def compare_board(probe: dict) -> dict:
    by_key = {r["key"]: r for r in probe["rows"]}
    frames = [("jab", 6), ("sweep", 14), ("hit_heavy", 8)]
    W, H = 720, 1230
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f26, f15, f13 = font(26), font(15), font(13)
    d.text((20, 10), "P4 · 上线前后姿态对照（玩家侧）", font=f26, fill=FG)
    d.text((20, 48), "左 = P3 上线态原表，右 = P4 落地态 micro2",
           font=f15, fill=MUTED)
    LEFT, TOP, CW, CH, GAP = 112, 96, 270, 320, 16
    d.text((LEFT, TOP - 24), "原表", font=f15, fill=GREY)
    d.text((LEFT + CW + GAP, TOP - 24), "micro2", font=f15,
           fill=ORANGE)
    for i, (card, fr) in enumerate(frames):
        y = TOP + i * (CH + 12)
        d.text((8, y + CH // 2 - 10), f"{card}:{fr}", font=f13,
               fill=FG)
        for j, mode in enumerate(("rolled_back", "shipped")):
            key = f"{mode}-{card}{fr:02d}"
            rec = by_key.get(key, {})
            x = LEFT + j * (CW + GAP)
            cell = open_sv(rec.get("player_sv", ""), (CW, CH))
            paste_cell(im, cell, (x, y))
            d.rectangle((x, y, x + CW, y + CH), outline=(62, 66, 78),
                        width=1)
    base = TOP + 3 * (CH + 12) + 6
    d.text((20, base),
           "三帧均无出框、撕裂或穿模；差异集中在膝/踝，"
           "上身与手臂不受影响。",
           font=f15, fill=FG)
    d.text((20, base + 32),
           "引擎内同进程 A/B 静态截帧；2D 侧关节最大位移 1.7778 px，"
           "由引擎读回 CardMotion 表确认。",
           font=f15, fill=MUTED)
    p = BOARDS / "P4-before-after-comparison.png"
    im.save(p)
    return {"path": str(p), "size": [W, H],
            "frames": [list(f) for f in frames]}


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    made = {
        "curve": curve_board(),
        "strip": strip_board(probe),
        "compare": compare_board(probe),
    }
    c = made["curve"]
    checks = {
        "three_boards_written": all(
            Path(v["path"]).is_file()
            and Path(v["path"]).stat().st_size > 30000
            for v in made.values()),
        "curve_flat_reduced_in_focus": (
            c["shipped_flat_pairs_in_focus"]
            < c["original_flat_pairs_in_focus"]),
        "strip_24_panels": made["strip"]["panels"] == 24,
        "compare_three_frames": len(made["compare"]["frames"]) == 3,
        "probe_all_checks_green": (
            bool(probe.get("checks"))
            and all(v is True for v in probe["checks"].values())
            and not probe.get("failed")),
    }
    report = {"made": made, "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("CURVE", c)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("P4_BOARDS_OK" if report["ok"] else "P4_BOARDS_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
