"""把 battle_motion_spec.json 的时间线画成「现状 vs 设计」对照图。

上半：现状（亮牌 1.5s + 结算 1.9s 里，动作只占 0.86s，其余站桩）
下半：设计（12 个事件填满 3.4s / 204 帧，赢家侧与输家侧分泳道）
所有区间从 spec 读，不写死坐标值；颜色只编码语义，不评美观。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "battle_motion_spec.json").read_text(encoding="utf-8"))
OUT = HERE / "战斗动作时间线.png"
STATS = HERE / "timeline_stats.json"

C = SPEC["constants"]
TOTAL = C["reveal_seconds"] + C["resolve_seconds"]
L, R = 190, 1740
W = R - L
H = 1000

BG = (247, 248, 250)
CARD = (255, 255, 255)
INK = (31, 36, 48)
SUB = (92, 100, 116)
GRID = (214, 219, 228)
IDLE = (233, 236, 241)
IDLE_EDGE = (208, 96, 82)
OLD_ACT = (151, 163, 184)
REVEAL = [(240, 201, 125), (232, 180, 92), (246, 220, 168)]
RESOLVE = [(126, 178, 193), (78, 143, 166), (176, 208, 217)]
LOSE = (214, 132, 116)
EX = (169, 139, 209)


def font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_TITLE, F_H, F_LABEL, F_SM, F_TINY = font(38), font(25), font(21), font(18), font(15)


def x(t):
    return int(L + t / TOTAL * W)


def wrap(s, n):
    return [s[i:i + n] for i in range(0, len(s), n)]


def bar(d, t0, t1, y0, y1, fill, label, outline=None, f=F_SM):
    a, b = x(t0), x(t1)
    d.rounded_rectangle([a, y0, b, y1], radius=6, fill=fill,
                        outline=outline, width=2 if outline else 1)
    if label and b - a > 26:
        cx = (a + b) // 2
        d.text((cx, (y0 + y1) // 2), label, font=f, fill=INK, anchor="mm")


img = Image.new("RGB", (1800, H), BG)
d = ImageDraw.Draw(img)

d.text((L, 30), "《牌拳》回合制战斗动作时间线：现状 vs 设计", font=F_TITLE, fill=INK)
d.text((L, 84), "一回 = 亮牌 1.5 s（90 帧）+ 结算 1.9 s（114 帧）= 3.4 s / 204 帧 · 60 fps",
       font=F_SM, fill=SUB)

# --- 刻度与阶段分隔 -------------------------------------------------------
AXIS_TOP, AXIS_BOT = 160, 720
for t in [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.4]:
    d.line([(x(t), AXIS_TOP), (x(t), AXIS_BOT)], fill=GRID, width=1)
    d.text((x(t), 138), f"{t:g}", font=F_SM, fill=SUB, anchor="mm")
d.line([(x(1.5), AXIS_TOP - 8), (x(1.5), AXIS_BOT + 16)], fill=(120, 130, 148), width=2)
d.text((x(0.75), 118), "reveal · 亮牌", font=F_LABEL, fill=SUB, anchor="mm")
d.text((x(2.45), 118), "resolve · 结算", font=F_LABEL, fill=SUB, anchor="mm")

# --- 现状 -----------------------------------------------------------------
d.text((30, 186), "现状", font=F_H, fill=INK)
d.text((30, 220), "arena.gd:652", font=F_TINY, fill=SUB)
y0, y1 = 180, 250
bar(d, 0.0, 1.5, y0, y1, IDLE, "")
bar(d, 0.0, 0.6, y0, y1, OLD_ACT, "ids[0] 招式 0.6s")
d.text((x(1.05), y1 + 8), "站桩 0.9s", font=F_SM, fill=IDLE_EDGE, anchor="mm")
bar(d, 1.5, 3.4, y0, y1, IDLE, "", outline=IDLE_EDGE)
bar(d, 1.5, 1.76, y0, y1, OLD_ACT, "")
d.text((x(1.63), y1 + 8), "hit_light 0.26s", font=F_TINY, fill=SUB, anchor="mm")
d.text((x(2.58), y0 + 35), "站桩 1.64s", font=F_LABEL, fill=IDLE_EDGE, anchor="mm")
# 结论句放在两行时间带之间的空白区，别压在灰条里的「站桩 1.64s」上
d.text((L, 288), "动作只占 0.86 / 3.4 s（25%），其余 2.54 s 站桩；赢家播哪张牌与胜负无关。",
       font=F_SM, fill=IDLE_EDGE)

# --- 设计：两条泳道 --------------------------------------------------------
win_y, lose_y = (370, 435), (455, 520)
d.text((30, 392), "设计", font=F_H, fill=INK)
d.text((30, 424), "赢家侧", font=F_SM, fill=SUB)
d.text((30, 478), "输家侧", font=F_SM, fill=SUB)

reveal_events = [
    (0.0, 0.18, "起势", REVEAL[0]),
    (0.18, 1.15, "亮牌 · 按牌型分三档", REVEAL[1]),
    (1.15, 1.5, "定格", REVEAL[2]),
]
for (yy0, yy1) in (win_y, lose_y):
    for t0, t1, label, col in reveal_events:
        bar(d, t0, t1, yy0, yy1, col, label, f=F_TINY if t1 - t0 < 0.3 else F_SM)
    bar(d, 1.5, 1.62, yy0, yy1, RESOLVE[2], "", f=F_TINY)
    if (yy0, yy1) == win_y:
        bar(d, 1.62, 2.22, yy0, yy1, RESOLVE[1], "赢家攻击 · 牌型决定", f=F_SM)
    else:
        bar(d, 1.62, 2.22, yy0, yy1, LOSE, "输家受击 · 伤害档", f=F_SM)
    bar(d, 2.22, 3.0, yy0, yy1, RESOLVE[0], "收势 / 恢复", f=F_SM)
    bar(d, 3.0, 3.4, yy0, yy1, RESOLVE[2], "回站架", f=F_TINY)

d.text((x(1.56), 538), "判定定格 0.12s", font=F_TINY, fill=SUB, anchor="mm")

# --- EX 覆盖行 -------------------------------------------------------------
d.text((30, 585), "EX 分支", font=F_SM, fill=EX)
ex_y = (575, 625)
bar(d, 0.0, 0.18, ex_y[0], ex_y[1], EX, "EX", f=F_TINY)
bar(d, 1.5, 1.62, ex_y[0], ex_y[1], EX, "", f=F_TINY)
d.text((x(0.32), 600), "p20 覆盖普通起势（仅 EX 侧）", font=F_SM, fill=SUB, anchor="lm")
d.text((x(1.9), 600), "p20 覆盖判定定格 → ex.burst", font=F_SM, fill=SUB, anchor="lm")

# --- 图例与底部说明 --------------------------------------------------------
legend = [("reveal 仪式段", REVEAL[1]), ("resolve 结算段", RESOLVE[1]),
          ("输家受击", LOSE), ("EX 覆盖", EX), ("现状站桩", IDLE)]
lx = L
for name, col in legend:
    d.rounded_rectangle([lx, 655, lx + 26, 675], radius=4, fill=col)
    d.text((lx + 34, 665), name, font=F_SM, fill=SUB, anchor="lm")
    lx += 210

boxes = [
    ("病灶", "现状动作取自亮牌第一张的 id，与牌型、与胜负都无关；赢家可能播后撤，输家可能播气功波。"),
    ("设计", "12 个事件填满 204 帧；亮牌只做仪式，赢家攻击与输家受击都在结算段；牌型决定动作强度与硬直档。"),
    ("边界", "规格层交付，游戏源码 0 改动；现成资产 7 项可用，新增 10 项未烘，3D 骨架可用性未证。"),
]
by = 710
for title, body in boxes:
    d.rounded_rectangle([L, by, R, by + 76], radius=8, fill=CARD, outline=GRID, width=1)
    d.text((L + 18, by + 18), title, font=F_LABEL, fill=INK)
    for i, line in enumerate(wrap(body, 74)):
        d.text((L + 92, by + 16 + i * 26), line, font=F_SM, fill=SUB)
    by += 86

img.save(OUT)


def union_len(intervals):
    """同一阶段内并行泳道 / EX 覆盖是重叠的，累加会把 3.4s 算成 4.3s。"""
    s = sorted(intervals)
    total, cur = 0.0, None
    for a, b in s:
        if cur is None:
            cur = [a, b]
        elif a <= cur[1]:
            cur[1] = max(cur[1], b)
        else:
            total += cur[1] - cur[0]
            cur = [a, b]
    if cur:
        total += cur[1] - cur[0]
    return total


covered = 0.0
for phase in ("reveal", "resolve"):
    iv = [(e["at_s"], e["until_s"]) for e in SPEC["events"]
          if e.get("phase_bound") == "timed" and e["phase"] == phase]
    covered += union_len(iv)
stats = {"file": OUT.name, "size": list(img.size), "bytes": OUT.stat().st_size,
         "total_seconds": TOTAL, "events": len(SPEC["events"]),
         "timed_covered_seconds": round(covered, 3),
         "coverage_pct": round(covered / TOTAL * 100, 1),
         "current_action_seconds": 0.86,
         "current_idle_seconds": round(TOTAL - 0.86, 2)}
STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"TIMELINE_OK {OUT.name} {img.size[0]}x{img.size[1]} "
      f"events={stats['events']} covered={stats['timed_covered_seconds']}s")
