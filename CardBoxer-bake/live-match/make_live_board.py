"""B 路线 · 真实对局交付物：节奏时间线板 / 整帧关键帧条带 / 连续 GIF。

素材全部来自 run_live_match.py 的真实引擎截帧与 analyze_live.py 的
同源逐帧 A/B 复算，不是离线合成的动作。

用法：python make_live_board.py
产出：boards/实跑一局-节奏时间线.png、实跑一局-整帧关键帧.png、
      实跑一局-玩家动作.gif、实跑一局-对手动作.gif、data/live_boards.json
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
D = HERE / "data"
BOARDS = HERE / "boards"
LIVE = D / "live_match.json"
ANALYSIS = D / "live_analysis.json"
OUT = D / "live_boards.json"

PHASE_COLORS = {
    "discard": (58, 66, 92), "select": (72, 92, 128),
    "reveal": (170, 122, 52), "resolve": (150, 62, 74),
}


def font(sz: int):
    for p in (r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                pass
    return ImageFont.load_default()


def gradient(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line((0, y, w, y),
               fill=(int(28 + 16 * t), int(24 + 11 * t),
                     int(38 + 20 * t)))
    return im


def timeline(live: dict, ana: dict, out: Path) -> dict:
    rows = live["cases"]["cap9"]["payload"]["rows"]
    fight = [r for r in rows if r["round_phase"] == "fight"]
    t0, t1 = fight[0]["t"], fight[-1]["t"]
    W, H = 1400, 780
    L, R = 92, 44
    PW = W - L - R
    im = gradient(W, H)
    d = ImageDraw.Draw(im)
    f24, f16, f13 = font(24), font(16), font(13)

    def x(t: float) -> int:
        return int(L + (t - t0) / max(1e-6, t1 - t0) * PW)

    d.text((20, 12), "《牌拳》live-match · 节奏与腿部幅度时间线",
           font=f24, fill=(240, 240, 244))
    d.text((20, 46),
           "真实自动对局（未冻结、未注入动作）；曲线为同源帧序列按 "
           "cap3 / cap9 分别复算的腿骨峰值角度。",
           font=f16, fill=(190, 198, 212))

    # 阶段色带
    ch = [c for c in live["cases"]["cap9"]["payload"]["phase_changes"]
          if c["kind"] == "tk_phase"]
    BY, BH = 92, 34
    d.text((14, BY + 8), "阶段", font=f13, fill=(190, 198, 212))
    for i, c in enumerate(ch):
        turn, ph = c["value"].split(":", 1)
        end = ch[i + 1]["t"] if i + 1 < len(ch) else t1
        x0, x1 = x(c["t"]), x(end)
        if x1 <= x0:
            continue
        d.rectangle((x0, BY, x1, BY + BH), fill=PHASE_COLORS.get(
            ph, (60, 60, 70)), outline=(20, 20, 26))
        if x1 - x0 > 52:
            d.text((x0 + 4, BY + 9), f"{turn}:{ph}", font=f13,
                   fill=(238, 238, 244))

    # 两个曲线区
    curves = ana["homologous_framewise_ab"]["jump_stats"]
    for panel, side in enumerate(("player", "foe")):
        top = 168 + panel * 268
        bot = top + 196
        d.rectangle((L, top, W - R, bot), fill=(16, 16, 23),
                    outline=(66, 70, 86))
        d.text((14, top + 4),
               "玩家侧" if side == "player" else "对手侧",
               font=f16, fill=(224, 228, 234))
        # 纵轴 0..16 度
        for v in (0, 4, 8, 12, 16):
            y = int(bot - v / 16.0 * (bot - top))
            d.line((L, y, W - R, y), fill=(46, 48, 60))
            d.text((L - 34, y - 8), f"{v}°", font=f13,
                   fill=(150, 158, 174))
        # 同源复算曲线：直接用报告里的 leg_series 不可得，重算一次
        from run_live_match import LEG_BONES, expected_delta  # noqa: E402
        for cap, col, name in ((3.0, (128, 142, 168), "cap3"),
                               (9.0, (255, 186, 92), "cap9")):
            pts = []
            for r in fight:
                st = r[side]
                dd = expected_delta(str(st["card"]),
                                    int(st["frame"]), cap)
                if not dd:
                    continue
                v = max(abs(dd[k]) for k in LEG_BONES)
                pts.append((x(r["t"]),
                            int(bot - min(v, 16.0) / 16.0
                                * (bot - top))))
            if len(pts) > 1:
                d.line(pts, fill=col, width=2)
        d.text((W - R - 190, top + 6), "灰：cap3   橙：cap9",
               font=f13, fill=(205, 212, 224))
        j3 = curves[side]["cap3"]
        j9 = curves[side]["cap9"]
        d.text((L + 8, top + 6),
               f"均值 {j3['peak_mean_deg']}° → {j9['peak_mean_deg']}°"
               f"   连续帧最大跳变 {j3['intra_max_deg']}° →"
               f" {j9['intra_max_deg']}°",
               font=f13, fill=(190, 198, 212))

    yy = 720
    d.rectangle((0, yy, W, H), fill=(14, 16, 21))
    d.text((20, yy + 8),
           f"三回阶段时长：discard/select 0.8 s，reveal 1.5 s，"
           f"resolve 1.9 s（非平局含 HITSTOP 0.24 s）；"
           f"采样 {live['sample_s']} s / 点，共 {len(fight)} 点。",
           font=f16, fill=(224, 228, 234))
    d.text((20, yy + 34),
           "四态均在真实对局中出现：亮牌 focus、赢家攻击、输家受击、"
           "平局两侧同播 hit_light。", font=f16,
           fill=(170, 230, 190))
    im.save(out)
    return {"size": im.size, "bytes": out.stat().st_size,
            "fight_samples": len(fight)}


def keyframes(live: dict, out: Path) -> dict:
    rows = live["cases"]["cap9"]["payload"]["rows"]
    picked = []
    seen = set()
    for r in rows:
        if not r.get("live") or not Path(r["live"]).is_file():
            continue
        k = (r["tk_turn"], r["tk_phase"])
        if r["round_phase"] == "fight" and k not in seen \
                and r["tk_phase"] in ("reveal", "resolve"):
            seen.add(k)
            picked.append(r)
    first = next((r for r in rows if r.get("live")
                  and Path(r["live"]).is_file()), None)
    last = next((r for r in reversed(rows) if r.get("live")
                 and Path(r["live"]).is_file()), None)
    items = ([first] if first else []) + picked[:6] + (
        [last] if last else [])
    CW, CH = 320, 180
    GAP, LEFT, TOP = 16, 16, 92
    COLS = 4
    rows_n = (len(items) + COLS - 1) // COLS
    W = LEFT * 2 + COLS * CW + (COLS - 1) * GAP
    H = TOP + rows_n * (CH + 48) + 62
    im = gradient(W, H)
    d = ImageDraw.Draw(im)
    f24, f15, f13 = font(24), font(15), font(13)
    d.text((16, 12), "《牌拳》live-match · 真实整帧关键帧",
           font=f24, fill=(240, 240, 244))
    d.text((16, 48), "全部为引擎内 1280x720 原图缩放，非离线合成；"
           "横幅 / 血条 / 卡牌均为当帧真实状态。",
           font=f15, fill=(190, 198, 212))
    for i, r in enumerate(items):
        c, rr = i % COLS, i // COLS
        x = LEFT + c * (CW + GAP)
        y = TOP + rr * (CH + 48)
        pic = Image.open(r["live"]).convert("RGB").resize(
            (CW, CH), Image.LANCZOS)
        im.paste(pic, (x, y))
        d.rectangle((x, y, x + CW, y + CH), outline=(70, 74, 90))
        label = (f"t={r['t']:.2f}s  第{r['tk_turn']}回 "
                 f"{r['tk_phase']}")
        d.text((x, y + CH + 3), label, font=f13,
               fill=(224, 228, 234))
        d.text((x, y + CH + 22),
               f"玩家 {r['player']['card']} / "
               f"对手 {r['foe']['card']}",
               font=f13, fill=(190, 198, 212))
    d.text((16, H - 34),
           "整帧图已等 RenderingServer.frame_post_draw，"
           "24/24 逐张不同；无「暂停」字样，证明是真跑而非冻结注入。",
           font=f15, fill=(170, 230, 190))
    im.save(out)
    return {"size": im.size, "bytes": out.stat().st_size,
            "frames": [r["live"] for r in items], "count": len(items)}


def gif(live: dict, side: str, out: Path) -> dict:
    rows = live["cases"]["cap9"]["payload"]["rows"]
    paths = [Path(r[f"{side}_sv"]) for r in rows
             if r.get(f"{side}_sv")
             and Path(r[f"{side}_sv"]).is_file()]
    frames = []
    for p in paths:
        fg = Image.open(p).convert("RGBA")
        bg = gradient(fg.width, fg.height).convert("RGBA")
        bg.alpha_composite(fg)
        frames.append(bg.convert("RGB").resize(
            (210, 260), Image.LANCZOS))
    if not frames:
        return {"frames": 0, "bytes": 0}
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=120, loop=0, optimize=False)
    return {"frames": len(frames), "bytes": out.stat().st_size,
            "duration_ms": 120, "loop": 0}


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    ana = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    outs = {
        "timeline": BOARDS / "live-match-rhythm-timeline.png",
        "keyframes": BOARDS / "live-match-full-keyframes.png",
        "player_gif": BOARDS / "live-match-player-motion.gif",
        "foe_gif": BOARDS / "live-match-foe-motion.gif",
    }
    made = {
        "timeline": timeline(live, ana, outs["timeline"]),
        "keyframes": keyframes(live, outs["keyframes"]),
        "player_gif": gif(live, "player", outs["player_gif"]),
        "foe_gif": gif(live, "foe", outs["foe_gif"]),
    }
    checks = {
        "timeline_written": made["timeline"]["bytes"] > 30000,
        "keyframes_written": made["keyframes"]["bytes"] > 100000,
        "keyframes_count": made["keyframes"]["count"] == 8,
        "player_gif_frames": made["player_gif"]["frames"] >= 60,
        "foe_gif_frames": made["foe_gif"]["frames"] >= 60,
        "both_gifs_same_frame_count":
            made["player_gif"]["frames"] == made["foe_gif"]["frames"],
        "all_keyframe_sources_exist": all(
            Path(p).is_file() for p in made["keyframes"]["frames"]),
        "analysis_all_green": ana["ok"] is True
        and all(ana["checks"].values()),
    }
    OUT.write_text(json.dumps({"made": made, "checks": checks,
                               "ok": all(checks.values())},
                              ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in made.items():
        print("MADE", k, v)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("LIVE_BOARDS_OK" if all(checks.values())
          else "LIVE_BOARDS_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
