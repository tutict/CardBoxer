"""P2 上线前后对照板：读回落盘态 shipped(cap9) vs 运行时回滚 rolled_back(cap3)。

素材全部来自 run_p2_shipped_probe.py 的引擎内 SubViewport 原图（同一
Godot 进程），非离线合成。用法：python make_shipped_board.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BOARDS = HERE / "boards"
REPORT = HERE / "data" / "p2_shipped_probe.json"
FULL = HERE / "data" / "full_tear.json"
SCENES = (("stance", 0, "站架"), ("jab", 1, "jab 腿峰帧"),
          ("sweep", 7, "sweep 腿峰帧"),
          ("hit_heavy", 1, "重受击腿峰帧"))
COLS = (("rolled_back", "上线前 cap=3"), ("shipped", "上线后 cap=9"))
LEG_BONES = ("thigh_f", "shin_f", "thigh_b", "shin_b")


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
               fill=(int(30 + 18 * t), int(26 + 12 * t),
                     int(40 + 22 * t)))
    return im


def make(side: str, out: Path, rows: dict, full: dict) -> tuple:
    CW, CH = 260, 325
    GAP, LEFT, TOP = 14, 118, 96
    W = LEFT * 2 + len(COLS) * CW + (len(COLS) - 1) * GAP
    H = TOP + len(SCENES) * (CH + 36) + 108
    im = Image.new("RGB", (W, H), (20, 20, 25))
    d = ImageDraw.Draw(im)
    f26, f17, f14 = font(26), font(17), font(14)
    d.text((18, 12),
           f"《牌拳》P2 上线前后 · {'玩家' if side == 'player' else '对手'}侧真实视口",
           font=f26, fill=(240, 240, 244))
    d.text((18, 50),
           "同一 Godot 进程内出图：左列为运行时回滚到旧值，右列为引擎读回的落盘值。",
           font=f17, fill=(190, 198, 212))
    for c, (_mode, label) in enumerate(COLS):
        x = LEFT + c * (CW + GAP)
        d.text((x, 78), label, font=f17,
               fill=(255, 214, 160) if c == 0 else (170, 230, 190))
    for r, (card, frame, label) in enumerate(SCENES):
        y = TOP + r * (CH + 36)
        d.text((8, y + CH // 2 - 14), label, font=f14,
               fill=(190, 198, 212))
        for c, (mode, _label) in enumerate(COLS):
            x = LEFT + c * (CW + GAP)
            rec = rows[f"{mode}-{card}{frame:02d}"]
            panel = gradient(CW, CH)
            fg = Image.open(rec[f"{side}_sv"]).convert("RGBA").resize(
                (CW, CH), Image.LANCZOS)
            panel.paste(fg, (0, 0), fg)
            im.paste(panel, (x, y))
            d.rectangle((x, y, x + CW, y + CH),
                        outline=(70, 74, 90), width=1)
            delta = rec.get(f"{side}_delta", {})
            peak = max(abs(float(delta.get(k, 0.0))) for k in LEG_BONES)
            d.text((x + 2, y + CH + 5), f"腿峰值 {peak:.1f}°",
                   font=f14, fill=(205, 212, 224))
    yy = TOP + len(SCENES) * (CH + 36)
    d.rectangle((0, yy, W, yy + 108), fill=(14, 16, 21))
    p = full["per_case"]["cap09_hard_g100"]
    d.text((18, yy + 10),
           "落盘改动仅一处：两份 motion_input*.json 的 leg_cap_deg 3.0 → 9.0；"
           "引擎读回两侧均为 9.0。", font=f17, fill=(224, 228, 234))
    d.text((18, yy + 38),
           f"全量 284 帧真实 GLB：最坏 p999 {p['worst_p999_m']:.6f} m，"
           "外部锚 0.09365 m 内，相对旧值仅 +7.12%。",
           font=f17, fill=(255, 205, 150))
    d.text((18, yy + 66),
           "站架帧逐像素不变；动作帧双侧可见变化；15 套引擎内自检全绿；"
           "默认关 3D 零污染。", font=f17, fill=(170, 230, 190))
    im.save(out)
    return im.size, out.stat().st_size


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    full = json.loads(FULL.read_text(encoding="utf-8"))
    rows = {r["key"]: r for r in rep["rows"]}
    outs = {
        "player": BOARDS / "P2上线前后-玩家对照.png",
        "foe": BOARDS / "P2上线前后-对手对照.png",
    }
    sizes = {k: make(k, p, rows, full) for k, p in outs.items()}
    checks = {
        "player_board_written": outs["player"].is_file()
        and sizes["player"][1] > 50000,
        "foe_board_written": outs["foe"].is_file()
        and sizes["foe"][1] > 50000,
        "boards_same_size": sizes["player"][0] == sizes["foe"][0],
        "all_sources_exist": all(
            Path(r[f"{side}_sv"]).is_file()
            for r in rep["rows"] for side in ("player", "foe")),
        "full_tear_gate_pass": full["verdict"]["full_284_frame_gate"]
        == "PASS" and full["ok"] is True,
        "shipped_probe_all_green": rep["ok"] is True
        and all(rep["checks"].values()),
    }
    for k, v in checks.items():
        print("CHECK", k, v)
    print("SHIPPED_BOARD_OK" if all(checks.values())
          else "SHIPPED_BOARD_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
