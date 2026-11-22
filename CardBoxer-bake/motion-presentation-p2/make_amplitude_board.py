"""P2 腿部幅度 · 引擎内 A/B 看图对照板（4 档 cap × 4 帧，玩家/对手各一张）。

素材全部来自 run_amplitude_p2_probe.py 的 SubViewport 原图，非离线合成。
用法：python make_amplitude_board.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BOARDS = HERE / "boards"
REPORT = HERE / "data" / "amplitude_p2_probe.json"
CAPS = (3, 6, 9, 12)
SCENES = (("stance", 0, "站架"), ("jab", 1, "jab 腿峰帧"),
          ("sweep", 7, "sweep 腿峰帧"),
          ("hit_heavy", 1, "重受击腿峰帧"))
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


def key(cap: int, card: str, frame: int) -> str:
    return f"cap{cap:02d}-{card}{frame:02d}"


def make(side: str, out: Path) -> tuple:
    rows = {r["key"]: r for r in
            json.loads(REPORT.read_text(encoding="utf-8"))["rows"]}
    CW, CH = 200, 250
    # 左侧留出行标签 gutter：首版 LEFT=20 且标签画在 y-22，
    # 与 y=74 的列标题和首格上沿重叠，看图复核时才发现。
    GAP, LEFT, TOP = 12, 118, 92
    W = LEFT * 2 + len(CAPS) * CW + (len(CAPS) - 1) * GAP
    H = TOP + len(SCENES) * (CH + 34) + 96
    im = Image.new("RGB", (W, H), (20, 20, 25))
    d = ImageDraw.Draw(im)
    f26, f17, f14 = font(26), font(17), font(14)
    d.text((18, 12),
           f"《牌拳》P2 腿部幅度 A/B · {'玩家' if side == 'player' else '对手'}侧真实视口",
           font=f26, fill=(240, 240, 244))
    d.text((18, 48),
           "四档 leg_cap_deg 由左至右；每格为引擎内 SubViewport 原图，"
           "标签是读回的腿部峰值角度。",
           font=f17, fill=(190, 198, 212))
    for c, cap in enumerate(CAPS):
        x = LEFT + c * (CW + GAP)
        tag = "线上基线" if cap == 3 else f"候选 cap={cap}"
        d.text((x, 74), tag, font=f17, fill=(255, 214, 160))
    for r, (card, frame, label) in enumerate(SCENES):
        y = TOP + r * (CH + 34)
        d.text((8, y + CH // 2 - 14), label, font=f14,
               fill=(190, 198, 212))
        for c, cap in enumerate(CAPS):
            x = LEFT + c * (CW + GAP)
            rec = rows[key(cap, card, frame)]
            panel = gradient(CW, CH)
            fg = Image.open(rec[f"{side}_sv"]).convert("RGBA").resize(
                (CW, CH), Image.LANCZOS)
            panel.paste(fg, (0, 0), fg)
            im.paste(panel, (x, y))
            d.rectangle((x, y, x + CW, y + CH),
                        outline=(70, 74, 90), width=1)
            delta = rec.get(f"{side}_delta", {})
            peak = max(abs(float(delta.get(k, 0.0))) for k in LEG_BONES)
            d.text((x + 2, y + CH + 4), f"腿峰值 {peak:.1f}°",
                   font=f14, fill=(205, 212, 224))
    yy = TOP + len(SCENES) * (CH + 34)
    d.rectangle((0, yy, W, yy + 96), fill=(14, 16, 21))
    d.text((18, yy + 10),
           "撕裂成本：cap 3→9 的最坏 p999 仅 +7%（0.04079→0.04369 m），"
           "腿幅度 ×3。", font=f17, fill=(224, 228, 234))
    d.text((18, yy + 38),
           "所有峰值帧都被硬 clamp 钉在 cap 上；看图重点判断腿是否出现"
           "「固定外撇 / 锁死」。", font=f17, fill=(255, 205, 150))
    d.text((18, yy + 66),
           "站架帧四档逐像素相同；本板不合成、不缩放原始动作数据，只缩放显示。",
           font=f17, fill=(170, 230, 190))
    im.save(out)
    return im.size, out.stat().st_size


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    outs = {
        "player": BOARDS / "P2-leg-amplitude-player-comparison.png",
        "foe": BOARDS / "P2-leg-amplitude-foe-comparison.png",
    }
    sizes = {k: make(k, p) for k, p in outs.items()}
    checks = {
        "player_board_written": outs["player"].is_file()
        and sizes["player"][1] > 50000,
        "foe_board_written": outs["foe"].is_file()
        and sizes["foe"][1] > 50000,
        "boards_same_size": sizes["player"][0] == sizes["foe"][0],
        "all_sources_exist": all(
            Path(r[f"{side}_sv"]).is_file()
            for r in json.loads(REPORT.read_text(
                encoding="utf-8"))["rows"]
            for side in ("player", "foe")),
    }
    for k, v in checks.items():
        print("CHECK", k, v)
    print("AMPLITUDE_BOARD_OK" if all(checks.values())
          else "AMPLITUDE_BOARD_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
