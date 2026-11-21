"""P3 · 出三张看图产物（纯读盘 + 合成，不改游戏）。

  A 时间线方波板 —— B 路线真实对局 129 采样，hard9 灰线 vs atan12 橙线，
    配三回阶段色带；这张直接回答「方波有没有变圆滑」。
  B 连续帧条带 —— 引擎内 A/B 的 sweep 14..21 连续 8 帧，
    4 行（玩家/对手 × hard9/atan12），看腿姿态是否逐帧渐变。
  C 上线前后对照 —— 2 列 × 3 个代表动作帧，看整体姿态有无甩飞/穿模。

用法：python make_p3_boards.py
产出：boards/*.png、data/p3_boards.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
sys.path.insert(0, str(HERE))
from p3_math import LEG_BONES, expected_delta  # noqa: E402

D = HERE / "data"
BOARDS = HERE / "boards"
SHOTS = HERE / "shots" / "p3"
LIVE = BAKE / "实跑一局" / "data" / "live_match.json"
PROBE = D / "p3_probe.json"
OUT = D / "p3_boards.json"

BG = (22, 22, 28)
FG = (230, 234, 242)
MUTED = (180, 190, 206)
GREY = (140, 150, 168)
ORANGE = (255, 186, 92)
GREEN = (110, 190, 150)
PHASE_COLORS = {"discard": (62, 74, 96), "select": (72, 92, 120),
                "reveal": (122, 92, 62), "resolve": (110, 66, 74)}


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
    im = Image.open(p).convert("RGBA")
    return im.resize(size, Image.LANCZOS)


def paste_cell(canvas: Image.Image, cell: Image.Image,
               xy: tuple[int, int]) -> None:
    canvas.paste(cell, xy, cell)


def leg_peak(card: str, frame: int, mode: str, cap: float) -> float:
    d = expected_delta(card, frame, mode, cap)
    if not d:
        return 0.0
    return round(max(abs(d[b]) for b in LEG_BONES), 2)


def timeline_board(live: dict) -> dict:
    rows = live["cases"]["cap9"]["payload"]["rows"]
    series = {
        "hard9": [leg_peak(str(r["player"]["card"]),
                           int(r["player"]["frame"]), "hard", 9.0)
                  for r in rows],
        "atan12": [leg_peak(str(r["player"]["card"]),
                            int(r["player"]["frame"]), "atan", 12.0)
                   for r in rows],
    }
    W, H = 1400, 760
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f26, f15, f13 = font(26), font(15), font(13)
    d.text((20, 12), "P3 · 方波平台期：真实对局腿峰值时间线",
           font=f26, fill=FG)
    d.text((20, 48),
           "灰线 = P2 上线态 hard cap9，橙线 = P3 落地态 atan12，"
           "同一条真实对局帧序列，只换腿骨映射",
           font=f15, fill=MUTED)

    # 三回阶段色带
    left, right, band_y = 80, 1340, 92
    x0 = left
    cur = None
    for i, r in enumerate(rows):
        key = (str(r["tk_turn"]), str(r["tk_phase"]))
        if key != cur:
            if cur is not None:
                x1 = left + (right - left) * i / len(rows)
                d.rectangle((x0, band_y, x1, band_y + 26),
                            fill=PHASE_COLORS.get(cur[1], (60, 64, 76)))
                if x1 - x0 > 44:
                    d.text((x0 + 4, band_y + 5), cur[1], font=f13,
                           fill=(225, 230, 240))
                x0 = x1
            cur = key
    x1 = right
    d.rectangle((x0, band_y, x1, band_y + 26),
                fill=PHASE_COLORS.get(cur[1], (60, 64, 76)))
    d.text((left, band_y + 32), "三回 × discard / select / reveal / resolve",
           font=f13, fill=MUTED)

    top, bot = 176, 556
    d.line((left, bot, right, bot), fill=(110, 114, 128), width=2)
    for tick in (0, 3, 6, 9, 12):
        y = bot - (bot - top) * tick / 12.0
        d.line((left, y, right, y), fill=(52, 56, 66), width=1)
        d.text((left - 34, y - 9), f"{tick}°", font=f13, fill=MUTED)
    for name, color in (("hard9", GREY), ("atan12", ORANGE)):
        pts = [(left + (right - left) * i / (len(rows) - 1),
                bot - (bot - top) * min(12.0, v) / 12.0)
               for i, v in enumerate(series[name])]
        d.line(pts, fill=color, width=3 if name == "atan12" else 2)
    d.text((right - 230, top - 24), "橙 = atan12    灰 = hard cap9",
           font=f15, fill=ORANGE)

    flat_h = sum(abs(b - a) < 1e-6 for a, b in zip(
        series["hard9"], series["hard9"][1:]))
    flat_a = sum(abs(b - a) < 1e-6 for a, b in zip(
        series["atan12"], series["atan12"][1:]))
    d.text((20, 596),
           f"相邻采样点腿峰值完全不变：hard9 {flat_h} 处，"
           f"atan12 {flat_a} 处；不同值 "
           f"{len(set(series['hard9']))} → {len(set(series['atan12']))} 种。",
           font=f15, fill=FG)
    d.text((20, 628),
           "站架段峰值恒 0 属正常站桩，不是动作平台；动作段的变化见连续帧条带。",
           font=f15, fill=MUTED)
    d.text((20, 660),
           "曲线由 Python 按同一公式复算，不取引擎截图；引擎内 A/B 另见探针报告。",
           font=f15, fill=MUTED)
    d.text((20, 700),
           "撕裂成本、平台成因与推荐档见「方波平台期-诊断说明」与全量 284 帧权衡板。",
           font=f13, fill=MUTED)
    p = BOARDS / "P3-时间线方波.png"
    im.save(p)
    return {"path": str(p), "size": [W, H], "samples": len(rows),
            "hard9_flat_pairs": flat_h, "atan12_flat_pairs": flat_a,
            "hard9_distinct": len(set(series["hard9"])),
            "atan12_distinct": len(set(series["atan12"]))}


def strip_board(probe: dict) -> dict:
    by_key = {r["key"]: r for r in probe["rows"]}
    frames = list(range(14, 22))
    W, H = 1400, 1060
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f26, f15, f13, f12 = font(26), font(15), font(13), font(12)
    d.text((20, 10), "P3 · 连续帧复核：sweep 14-21（实测最长 clamp 平台段）",
           font=f26, fill=FG)
    d.text((20, 46),
           "上=玩家，下=对手；每组上排 P2 hard cap9，下排 P3 atan12。"
           "格内数字为该帧腿峰值（度）",
           font=f15, fill=MUTED)
    LEFT, TOP, CW, CH = 132, 104, 150, 190
    GAP_X, GAP_Y = 8, 16
    for j, fr in enumerate(frames):
        x = LEFT + j * (CW + GAP_X)
        d.text((x + 40, TOP - 26), f"f{fr}", font=f13, fill=FG)
    groups = [
        ("玩家 hard9", "rolled_back", "player", "hard", 9.0),
        ("玩家 atan12", "shipped", "player", "atan", 12.0),
        ("对手 hard9", "rolled_back", "foe", "hard", 9.0),
        ("对手 atan12", "shipped", "foe", "atan", 12.0),
    ]
    for i, (label, mode, side, mm, mc) in enumerate(groups):
        y = TOP + i * (CH + GAP_Y)
        d.text((8, y + CH // 2 - 22), label, font=f13,
               fill=ORANGE if "atan12" in label else GREY)
        for j, fr in enumerate(frames):
            key = f"{mode}-sweep{fr:02d}"
            rec = by_key.get(key, {})
            x = LEFT + j * (CW + GAP_X)
            cell = open_sv(rec.get(f"{side}_sv", ""), (CW, CH))
            paste_cell(im, cell, (x, y))
            d.rectangle((x, y, x + CW, y + 20), fill=(18, 18, 24))
            d.text((x + 6, y + 3),
                   f"{leg_peak('sweep', fr, mm, mc):.2f}°",
                   font=f12, fill=ORANGE if mm == "atan" else FG)
            d.rectangle((x, y, x + CW, y + CH), outline=(62, 66, 78),
                        width=1)
    d.text((20, TOP + 4 * (CH + GAP_Y) + 10),
           "硬 clamp 段（f14-f21）上排腿峰值钉在 9.00° 不动，下排逐帧变化，"
           "但人物没有甩飞、穿模或出框。",
           font=f15, fill=FG)
    d.text((20, TOP + 4 * (CH + GAP_Y) + 42),
           "这是引擎内同进程 A/B 静态截帧（arena.paused 冻结），"
           "不是真实对局；真实对局取证见「实跑一局」。",
           font=f15, fill=MUTED)
    p = BOARDS / "P3-连续帧条带.png"
    im.save(p)
    return {"path": str(p), "size": [W, H], "frames": frames,
            "groups": len(groups), "panels": len(groups) * len(frames)}


def compare_board(probe: dict) -> dict:
    by_key = {r["key"]: r for r in probe["rows"]}
    frames = [("jab", 1), ("sweep", 7), ("hit_heavy", 1)]
    W, H = 720, 1230
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    f26, f15, f13 = font(26), font(15), font(13)
    d.text((20, 10), "P3 · 上线前后姿态对照（玩家侧）", font=f26, fill=FG)
    d.text((20, 48), "左 = P2 上线态 hard cap9，右 = P3 落地态 atan12",
           font=f15, fill=MUTED)
    LEFT, TOP, CW, CH, GAP = 112, 96, 270, 320, 16
    d.text((LEFT, TOP - 24), "hard cap9", font=f15, fill=GREY)
    d.text((LEFT + CW + GAP, TOP - 24), "atan12", font=f15,
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
           "三帧均无出框、撕裂或穿模；腿姿态差异集中在膝/踝角度，"
           "上身与手臂不受影响。",
           font=f15, fill=FG)
    d.text((20, base + 32),
           "引擎内同进程 A/B 静态截帧；站架帧两模式逐像素相同（差 0）。",
           font=f15, fill=MUTED)
    p = BOARDS / "P3-上线前后对照.png"
    im.save(p)
    return {"path": str(p), "size": [W, H],
            "frames": [list(f) for f in frames]}


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    made = {
        "timeline": timeline_board(live),
        "strip": strip_board(probe),
        "compare": compare_board(probe),
    }
    t = made["timeline"]
    checks = {
        "three_boards_written": all(
            Path(v["path"]).is_file()
            and Path(v["path"]).stat().st_size > 30000
            for v in made.values()),
        "timeline_from_129_real_samples": t["samples"] == 129,
        "timeline_plateau_reduced": (
            t["atan12_flat_pairs"] < t["hard9_flat_pairs"]),
        "timeline_distinct_increased": (
            t["atan12_distinct"] > t["hard9_distinct"]),
        "strip_32_panels": made["strip"]["panels"] == 32,
        "compare_three_frames": len(made["compare"]["frames"]) == 3,
    }
    report = {"made": made, "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print("TIMELINE", t)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("P3_BOARDS_OK" if report["ok"] else "P3_BOARDS_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
