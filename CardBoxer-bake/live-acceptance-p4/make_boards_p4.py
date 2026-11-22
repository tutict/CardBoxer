"""P4 · 实机验收 · 三张看图板（纯读盘，不重跑 Godot）。

  P4-live-rhythm-timeline.png   真跑 128 点的 tk_phase 带 + 腿峰值/跳变曲线，
                          P3 灰（同源复算）/ P4 橙（真跑读回）
  P4-live-frame-sequence-strip.png   真跑连续 6 个采样点的玩家/对手 SV 原图，
                          每格标 P3 与 P4 的 thigh_f 角度
  P4-live-full-keyframes.png   3D 开态与默认关各 3 张真实整帧

字体避开 U+21D2（微软雅黑缺字方框）；板材只缩放，不重绘人物。
产出：boards/*.png、data/boards_p4.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
D = HERE / "data"
BOARDS = HERE / "boards"
OUT = D / "boards_p4.json"
LIVE = json.loads((D / "live_p4.json").read_text(encoding="utf-8"))
ANA = json.loads((D / "live_p4_analysis.json").read_text(encoding="utf-8"))

BG = "#14171c"
PANEL = "#1e232b"
LINE = "#2b323d"
TEXT = "#e8eaf0"
MUTED = "#8b93a3"
ORANGE = "#f0a44a"
GRAY = "#8d97a8"
GREEN = "#59c28a"
PHASE_COLORS = {"discard": "#3a4354", "select": "#3f4d61",
                "reveal": "#5a4a34", "resolve": "#6d4530"}


def font(sz: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).is_file():
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def paste_fit(canvas: Image.Image, path: Path, box: tuple) -> None:
    x, y, w, h = box
    im = Image.open(path).convert("RGB")
    r = min(w / im.width, h / im.height)
    nw, nh = max(1, int(im.width * r)), max(1, int(im.height * r))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas.paste(im, (x + (w - nw) // 2, y + (h - nh) // 2))


def text(d: ImageDraw.ImageDraw, xy, s: str, sz: int,
         color: str = TEXT) -> None:
    d.text(xy, s, font=font(sz), fill=color)


def board_timeline() -> dict:
    # 看图迭代（第 2 版）：首版把 P3/P4 画在 10° 量级主图上，0.1° 差异
    # 被完全压平、两条线看着重合，等于没展示 P4 的效果。补两个独立纵轴
    # 面板：逐帧 |P4−P3| 差、focus 定格段放大。与 P4 静态曲线板同一教训。
    W, H = 1460, 960
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    text(d, (36, 24), "P4 · 实机验收：真实自动对局节奏时间线（3D 开态）", 25)
    text(d, (36, 60), "不冻结、不注入；灰线＝同一帧序列按 P3 原表复算，橙线＝P4 落盘表真跑读回",
         15, MUTED)

    rows = LIVE["cases"]["three_d"]["payload"]["rows"]
    curves = ANA["curves"]["player"]
    t0, t1 = rows[0]["t"], rows[-1]["t"]
    PX, PW = 40, 980
    def X(t: float) -> int:
        return PX + int((t - t0) / max(t1 - t0, 1e-6) * PW)

    # ── 阶段带 ──
    band_y, band_h = 100, 26
    ch = [c for c in LIVE["cases"]["three_d"]["payload"]["phase_changes"]
          if c["kind"] == "tk_phase"]
    for i, c in enumerate(ch):
        a = c["t"]
        b = ch[i + 1]["t"] if i + 1 < len(ch) else t1
        ph = c["value"].split(":", 1)[1]
        d.rectangle([X(a), band_y, X(b), band_y + band_h],
                    fill=PHASE_COLORS.get(ph, PANEL))
        if X(b) - X(a) > 34:
            text(d, (X(a) + 4, band_y + 5), ph, 11, TEXT)
    text(d, (PX, band_y - 22), "回合阶段", 14, MUTED)

    # ── 腿峰值曲线（P3/P4 在此重合属实）──
    y0, y1 = 160, 310
    d.rectangle([PX, y0, PX + PW, y1], fill=PANEL)
    peaks = [p["leg_peak"] for p in curves["p3"] + curves["p4"]]
    pmax = max(peaks + [1.0]) * 1.1
    def Y(v: float) -> int:
        return y1 - int(v / pmax * (y1 - y0))
    for g in (0.25, 0.5, 0.75):
        gy = Y(pmax * g)
        d.line([PX, gy, PX + PW, gy], fill=LINE, width=1)
    for which, col in (("p3", GRAY), ("p4", ORANGE)):
        d.line([(X(p["t"]), Y(p["leg_peak"]))
                for p in curves[which]], fill=col, width=2)
    text(d, (PX, y0 - 22),
         "腿骨峰值 |delta|（度）  灰＝P3  橙＝P4，10° 纵轴上两线重合属实",
         14, MUTED)

    # ── 逐采样点跳变 ──
    y2, y3 = 352, 500
    d.rectangle([PX, y2, PX + PW, y3], fill=PANEL)
    def jumps_of(which: str):
        s = curves[which]
        return [(b["t"], max(abs(b["legs"][k] - a["legs"][k])
                             for k in b["legs"]))
                for a, b in zip(s, s[1:])]
    j3, j4 = jumps_of("p3"), jumps_of("p4")
    jmax = max([v for _, v in j3 + j4] + [1.0]) * 1.1
    def YJ(v: float) -> int:
        return y3 - int(v / jmax * (y3 - y2))
    for g in (0.25, 0.5, 0.75):
        gy = YJ(jmax * g)
        d.line([PX, gy, PX + PW, gy], fill=LINE, width=1)
    for series, col in ((j3, GRAY), (j4, ORANGE)):
        d.line([(X(t), YJ(v)) for t, v in series], fill=col, width=2)
    text(d, (PX, y2 - 22),
         "相邻采样点腿骨跳变（度）  灰＝P3  橙＝P4，峰值反而略降", 14, MUTED)
    for turn in ("1", "2", "3"):
        first = next((c["t"] for c in ch
                      if c["value"].startswith(turn + ":")), None)
        if first is None:
            continue
        x = X(first)
        # 只画竖线：首版在带下方写「第 N 回」会压住下一个面板的标题，
        # 回合边界由竖线 + 阶段色块表达，脚注里点名。
        d.line([x, band_y, x, y3], fill="#3b4351", width=1)

    # ── 面板 3：逐帧 |P4−P3| 差（独立纵轴，直接展示 P4 改动落在哪里）──
    y4, y5 = 540, 660
    d.rectangle([PX, y4, PX + PW, y5], fill=PANEL)
    diffs = [(b["t"], max(abs(b["legs"][k] - a["legs"][k])
                          for k in b["legs"]))
             for a, b in zip(curves["p3"], curves["p4"])]
    dmax = max([v for _, v in diffs] + [0.1]) * 1.15
    def YD(v: float) -> int:
        return y5 - int(v / dmax * (y5 - y4))
    for g in (0.25, 0.5, 0.75):
        gy = YD(dmax * g)
        d.line([PX, gy, PX + PW, gy], fill=LINE, width=1)
    d.line([(X(t), YD(v)) for t, v in diffs], fill=ORANGE, width=2)
    text(d, (PX, y4 - 22),
         "逐帧 |P4 − P3| 腿骨差（度）  只在 P4 改动帧非零，上界 1.870°",
         14, MUTED)
    text(d, (PX + 6, y4 + 6), "%.3f" % dmax, 12, MUTED)
    text(d, (PX + 6, y5 - 20), "0", 12, MUTED)

    # ── 面板 4：focus 定格段放大（P3 水平 / P4 逐帧分开）──
    y6, y7 = 700, 840
    d.rectangle([PX, y6, PX + PW, y7], fill=PANEL)
    # 只取一段 idx 连续的定格段：首版把三个回合的同名 focus 帧串成
    # 一条折线，且 x 轴误标成采样序号，是误导性的图，必须按段切开。
    focus_all = []
    for a, b in zip(curves["p3"], curves["p4"]):
        if (a["card"] == "focus"
                and a["legs"]["thigh_f"] < -9.2):
            focus_all.append((a["idx"], a["t"], a["frame"],
                              a["legs"]["thigh_f"],
                              b["legs"]["thigh_f"]))
    segs: list = []
    cur: list = []
    for r in focus_all:
        if cur and r[0] == cur[-1][0] + 1:
            cur.append(r)
        else:
            cur = [r]
        segs.append(list(cur))
    focus = max(segs, key=len)[:8] if segs else []
    vals = [v for _, _, _, v3, v4 in focus
            for v in (v3, v4)] or [-9.3, -9.2]
    lo, hi = min(vals) - 0.03, max(vals) + 0.03
    def YF(v: float) -> int:
        return y7 - int((v - lo) / max(hi - lo, 1e-6) * (y7 - y6))
    if focus:
        fx0, fx1 = PX + 60, PX + PW - 60
        step = (fx1 - fx0) / max(len(focus) - 1, 1)
        for series, col in ((3, GRAY), (4, ORANGE)):
            pts = [(fx0 + i * step, YF(r[series]))
                   for i, r in enumerate(focus)]
            d.line(pts, fill=col, width=2)
            for px, py in pts:
                d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=col)
        for i, r in enumerate(focus):
            px = fx0 + i * step
            text(d, (px - 20, y7 - 22), "f%d" % r[2], 11, MUTED)
            text(d, (px - 30, YF(r[4]) - 20),
                 "%.3f" % r[4], 11, ORANGE)
    text(d, (PX, y6 - 22),
         "focus 定格段放大：thigh_f（度）  灰＝P3 水平定格，橙＝P4 逐帧分开",
         14, MUTED)
    # 说明放标题行右侧：放面板内会正好压在灰线（P3 恒值靠近纵轴上沿）。
    text(d, (PX + 520, y6 - 22),
         "单段连续帧；P3 恒 %.3f°，纵轴仅 %.3f ~ %.3f°" % (
             focus[0][3] if focus else 0.0, lo, hi), 12, MUTED)
    text(d, (PX, 856), "时间（秒，真跑墙钟）；第 1 回 discard 记在 intro 内，带内首段是 select",
         13, MUTED)

    # ── 右侧数字卡 ──
    cx, cw = 1050, 374
    cards = [
        ("真跑采样点", str(len(rows)) + " 点 / 0.12 s"),
        ("精确平台 玩家", "81 → 72，下降 9 对"),
        ("精确平台 对手", "83 → 74，下降 9 对"),
        ("最大跳变 玩家", "13.661 → 13.642°"),
        ("最大跳变 对手", "14.662 → 14.634°"),
        ("最大额外跳变", "+0.727° / +0.893°"),
        ("静态上界 D_static", "1.870° @wave:34"),
        ("实机最大 |P4−P3|", "1.653°，在上界内"),
        ("两局终局 HP", "85:80 / 97:63（不同）"),
    ]
    cy = 100
    for name, val in cards:
        d.rectangle([cx, cy, cx + cw, cy + 62], fill=PANEL)
        text(d, (cx + 12, cy + 8), name, 14, MUTED)
        text(d, (cx + 12, cy + 31), val, 17,
             GREEN if "下降" in val or "上界内" in val else TEXT)
        cy += 69

    foot = [
        "两次独立 Godot 进程真跑，paused 全程 false；阶段带上的竖线是回合边界；跨进程 RNG 漂移（终局 HP 不同），不做逐帧像素 A/B。",
        "P3 曲线是同一份真跑 (card, frame) 序列按 P3 原表复算；连续帧跳变首次量化、无历史外部锚，只报分布不设放行线。",
        "实机采样 0.12 s 间隔，这里的「平台」口径是相邻采样点腿骨 delta 差，与静态全量 284 帧的相邻帧平台不同。",
        "首版把 0.1° 差异画在 10° 主图上导致两线重合；补独立纵轴的逐帧差与定格段放大面板后才可辨。",
    ]
    for i, s in enumerate(foot):
        text(d, (36, 872 + i * 22), s, 12, MUTED)
    p = BOARDS / "P4-live-rhythm-timeline.png"
    im.save(p)
    return {"path": str(p), "sha256": sha(p), "size": list(im.size),
            "focus_zoom_points": len(focus),
            "focus_zoom_frames": [r[2] for r in focus]}


def pick_strip(rows: list) -> list:
    """优先挑 focus 定格段的连续 6 个采样点（P4 改动帧最集中）。"""
    sv = [r for r in rows if r.get("player_sv") and r.get("foe_sv")]
    best: list = []
    cur: list = []
    for r in sv:
        if cur and r["idx"] == cur[-1]["idx"] + 1:
            cur.append(r)
        else:
            cur = [r]
        if len(cur) > len(best):
            best = list(cur)
    def score(group):
        return sum(1 for r in group if r["player"]["card"] == "focus")
    candidates = []
    for i in range(len(sv) - 5):
        g = sv[i:i + 6]
        if all(g[j + 1]["idx"] == g[j]["idx"] + 1 for j in range(5)):
            candidates.append(g)
    if candidates:
        return max(candidates, key=score)
    return best[:6]


def board_strip() -> dict:
    rows = LIVE["cases"]["three_d"]["payload"]["rows"]
    strip = pick_strip(rows)
    curves = ANA["curves"]["player"]
    foes = ANA["curves"]["foe"]
    by_idx = {p["idx"]: p for p in curves["p3"]}
    by_idx4 = {p["idx"]: p for p in curves["p4"]}
    f3 = {p["idx"]: p for p in foes["p3"]}
    f4 = {p["idx"]: p for p in foes["p4"]}
    W, H = 1440, 910
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    text(d, (36, 22), "P4 · 实机连续帧条带（真实对局，非冻结注入）", 25)
    text(d, (36, 58), "每格为真跑读回的 SubViewport 原图；角度是同一帧按 P3 原表 / P4 落盘表分别复算",
         15, MUTED)
    CW, CH, GAP, X0, Y0 = 218, 270, 12, 36, 104
    for row, (key, tag) in enumerate((("player_sv", "玩家"),
                                      ("foe_sv", "对手"))):
        text(d, (X0, Y0 + row * (CH + 62) - 20), tag, 14, MUTED)
        for col, r in enumerate(strip):
            x = X0 + col * (CW + GAP)
            y = Y0 + row * (CH + 62)
            d.rectangle([x, y, x + CW, y + CH], fill=PANEL)
            paste_fit(im, Path(r[key]), (x + 2, y + 2, CW - 4, CH - 4))
            idx = r["idx"]
            a3, a4 = by_idx.get(idx), by_idx4.get(idx)
            b3, b4 = f3.get(idx), f4.get(idx)
            p3v = a3["legs"]["thigh_f"] if a3 else None
            p4v = a4["legs"]["thigh_f"] if a4 else None
            f3v = b3["legs"]["thigh_f"] if b3 else None
            f4v = b4["legs"]["thigh_f"] if b4 else None
            text(d, (x, y + CH + 4),
                 "#%04d  t=%.2f  %s:%d" % (
                     idx, r["t"], r[key.replace("_sv", "")]["card"],
                     r[key.replace("_sv", "")]["frame"]), 12, TEXT)
            if row == 0 and p3v is not None:
                text(d, (x, y + CH + 24),
                     "thigh_f  P3 %.3f → P4 %.3f" % (p3v, p4v),
                     12, ORANGE)
            if row == 1 and f3v is not None:
                text(d, (x, y + CH + 24),
                     "thigh_f  P3 %.3f → P4 %.3f" % (f3v, f4v),
                     12, ORANGE)
    foot = [
        "上排玩家 / 下排对手；同一列是同一时刻、同一 (card, frame)，只有动作表不同（P3 为复算值，不重跑第二局）。",
        "前 3 格不在 P4 的 109 个改动帧里，所以 P3 与 P4 角度相同；后 3 格是 focus 定格段，P3 恒为 −9.238°、P4 逐帧分开。",
        "双方同卡同帧且两版表 11 关节同步，腿骨 delta 对称相等，因此上下两行角度数值相同，不是复制粘贴。",
        "P4 在定格段内给了不足 2 px 的逐帧扰动；上身与手臂不受影响，人物无甩飞、穿模或出框。",
    ]
    for i, s in enumerate(foot):
        text(d, (36, 782 + i * 26), s, 13, MUTED)
    p = BOARDS / "P4-live-frame-sequence-strip.png"
    im.save(p)
    return {"path": str(p), "sha256": sha(p), "size": list(im.size),
            "picked_idx": [r["idx"] for r in strip],
            "picked_cards": [r["player"]["card"] for r in strip]}


def board_keyframes() -> dict:
    W, H = 1400, 850
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    text(d, (36, 22), "P4 · 实机整帧关键帧：3D 开态 vs 默认关 2D", 25)
    text(d, (36, 58), "两行来自两次独立真跑；默认关时 2D 关节表才参与绘制，是 P4 数据层改动的唯一可见侧",
         15, MUTED)
    CW, CH, GAP, X0, Y0 = 428, 241, 16, 36, 104
    picks = {}
    for tag in ("three_d", "default_off"):
        rows = LIVE["cases"][tag]["payload"]["rows"]
        lv = [r for r in rows if r.get("live")
              and r["tk_phase"] in ("reveal", "resolve")]
        # 均匀取 3 张，保证覆盖 reveal 与 resolve
        if len(lv) >= 3:
            sel = [lv[0], lv[len(lv) // 2], lv[-1]]
        else:
            sel = lv
        picks[tag] = sel
    for row, tag in enumerate(("three_d", "default_off")):
        label = "3D 开态（CARD_BOXER_3D=1）" if tag == "three_d" \
            else "默认关（2D 火柴人 + HUD）"
        text(d, (X0, Y0 + row * (CH + 74) - 22), label, 15, MUTED)
        for col, r in enumerate(picks[tag]):
            x = X0 + col * (CW + GAP)
            y = Y0 + row * (CH + 74)
            d.rectangle([x, y, x + CW, y + CH], fill=PANEL)
            paste_fit(im, Path(r["live"]), (x + 2, y + 2, CW - 4, CH - 4))
            text(d, (x, y + CH + 6),
                 "#%04d  t=%.2f  第%d回 %s" % (
                     r["idx"], r["t"], r["tk_turn"], r["tk_phase"]),
                 13, TEXT)
            text(d, (x, y + CH + 28),
                 "HP %d : %d" % (r["hp"][0], r["hp"][1]), 12, MUTED)
    foot = [
        "两局均打完三回、paused 全程 false，整帧无「暂停」字样（与 P1/P2/P3 冻结探针的板子不同）。",
        "中文无乱码 / 缺字方框；两名角色分离、无重叠；默认关侧 2D 火柴人正常，无甩飞或穿模。",
        "同一 #idx 只是采样序号对齐，不代表同一牌局；格子里的 HP 是该帧血量，不是终局血量。",
        "跨进程终局 HP 不同（85:80 / 97:63），只各自看画面健康度，不做逐帧像素 A/B。",
    ]
    for i, s in enumerate(foot):
        text(d, (36, 726 + i * 26), s, 13, MUTED)
    p = BOARDS / "P4-live-full-keyframes.png"
    im.save(p)
    return {"path": str(p), "sha256": sha(p), "size": list(im.size),
            "picked": {tag: [r["idx"] for r in sel]
                       for tag, sel in picks.items()},
            "phases": {tag: [r["tk_phase"] for r in sel]
                       for tag, sel in picks.items()}}


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    a = board_timeline()
    b = board_strip()
    c = board_keyframes()
    all_rows = {r["idx"] for r in
                LIVE["cases"]["three_d"]["payload"]["rows"]}
    checks = {
        "three_boards_valid_png_signature": all(
            Path(x["path"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            for x in (a, b, c)),
        "three_boards_nonempty": all(
            Path(x["path"]).stat().st_size > 10000 for x in (a, b, c)),
        "strip_six_continuous_frames": (
            len(b["picked_idx"]) == 6
            and all(b["picked_idx"][i + 1] == b["picked_idx"][i] + 1
                    for i in range(5))
            and all(i in all_rows for i in b["picked_idx"])),
        "keyframes_picked_from_both_tags": all(
            len(v) == 3 for v in c["picked"].values()),
        "keyframes_cover_reveal_and_resolve": all(
            "reveal" in v and "resolve" in v
            for v in c["phases"].values()),
        "timeline_zoom_is_single_continuous_segment": (
            len(a.get("focus_zoom_frames", [])) >= 2
            and len(a["focus_zoom_frames"]) <= 8
            and all(a["focus_zoom_frames"][i + 1]
                    > a["focus_zoom_frames"][i]
                    for i in range(len(a["focus_zoom_frames"]) - 1))),
        "timeline_numbers_match_analysis": (
            ANA["sample_count"] == 128
            and ANA["jump_stats"]["player"]["p3"]["exact_flat_pairs"] == 81
            and ANA["jump_stats"]["player"]["p4"]["exact_flat_pairs"] == 72
            and ANA["jump_stats"]["foe"]["p3"]["exact_flat_pairs"] == 83
            and ANA["jump_stats"]["foe"]["p4"]["exact_flat_pairs"] == 74),
        "upstream_live_and_analysis_all_checks_true": all(
            all(v is True for v in rep["checks"].values())
            and not rep["failed"] and rep["ok"] is True
            for rep in (LIVE, ANA)),
    }
    report = {"boards": {"timeline": a, "strip": b, "keyframes": c},
              "checks": checks,
              "failed": [k for k, v in checks.items() if not v],
              "ok": all(checks.values())}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("BOARD_PATHS", [x["path"] for x in (a, b, c)])
    print("P4_LIVE_BOARDS_OK" if report["ok"] else "P4_LIVE_BOARDS_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
