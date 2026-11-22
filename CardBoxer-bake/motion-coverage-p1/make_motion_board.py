"""P1 动作覆盖 · 两张看图对照板（素材全部来自引擎内真实截帧）。

  boards/motion-coverage-six-state-viewport-comparison.png   6 场景 × 玩家/对手两层 SubViewport 原图
  boards/motion-coverage-combat-frame-comparison.png     5 场景整帧（含 HUD）缩略

用法：python make_motion_board.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "p1"
BOARDS = HERE / "boards"
REPORT = HERE / "data" / "motion_p1_probe.json"
OUT1 = BOARDS / "motion-coverage-six-state-viewport-comparison.png"
OUT2 = BOARDS / "motion-coverage-combat-frame-comparison.png"

SCENES = ["stance", "reveal", "player_win", "enemy_win", "draw",
          "legacy_player_win"]
LABELS = ["① 站架", "② 亮牌", "③ 玩家赢", "④ 对手赢", "⑤ 平局",
          "⑥ 裁回3卡A/B"]


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


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    rows = {r["id"]: r for r in
            json.loads(REPORT.read_text(encoding="utf-8"))["rows"]}

    # 板 1：6 列 × 2 行 SubViewport 原图
    CW, CH = 176, 220
    GAP, LEFT, TOP = 10, 18, 62
    W = LEFT * 2 + 6 * CW + 5 * GAP
    H = TOP + 2 * (CH + 28) + 96
    b1 = Image.new("RGB", (W, H), (20, 20, 25))
    d = ImageDraw.Draw(b1)
    f26, f17, f14 = font(26), font(17), font(14)
    d.text((18, 14), "《牌拳》3D 动作覆盖 · 六态双层视口原图",
           font=f26, fill=(240, 240, 242))
    for c, sid in enumerate(SCENES):
        x = LEFT + c * (CW + GAP)
        d.text((x, 44), LABELS[c], font=f17, fill=(255, 214, 160))
    for r, side in enumerate(("player", "foe")):
        y = TOP + r * (CH + 28)
        for c, sid in enumerate(SCENES):
            x = LEFT + c * (CW + GAP)
            panel = gradient(CW, CH)
            src = Path(rows[sid][f"{side}_sv"])
            fg = Image.open(src).convert("RGBA").resize(
                (CW, CH), Image.LANCZOS)
            panel.paste(fg, (0, 0), fg)
            b1.paste(panel, (x, y))
            d.rectangle((x, y, x + CW, y + CH),
                        outline=(70, 74, 90), width=1)
            rec = rows[sid]
            d.text((x + 2, y + CH + 4),
                   f"{'玩家' if side == 'player' else '对手'}: "
                   f"{rec[f'{side}_card']} {rec[f'{side}_frame']}",
                   font=f14, fill=(205, 212, 224))
    yy = TOP + 2 * (CH + 28)
    d.rectangle((0, yy, W, yy + 96), fill=(14, 16, 21))
    d.text((18, yy + 10),
           "改前只有 ③ 玩家赢 / ④ 对手赢 的赢家在动；现在 ② 亮牌、"
           "③④ 输家受击、⑤ 平局全部有动作。",
           font=f17, fill=(224, 228, 234))
    d.text((18, yy + 38),
           "⑥ 是运行时把动作表裁回旧 3 卡的 A/B：赢家帧与 ③ 逐字节相同，"
           "证明攻击侧零回归；对手退回站架。",
           font=f17, fill=(170, 230, 190))
    d.text((18, yy + 66),
           "素材为引擎内 SubViewport 原图，非离线合成；两层各自独立 World3D。",
           font=f17, fill=(255, 205, 150))
    b1.save(OUT1)

    # 板 2：5 场景整帧缩略（3 列 × 2 行）
    LW, LH = 400, 225
    W2, H2 = 18 * 2 + 3 * LW + 2 * 12, 56 + 2 * (LH + 30) + 64
    b2 = Image.new("RGB", (W2, H2), (20, 20, 25))
    d2 = ImageDraw.Draw(b2)
    d2.text((18, 12), "《牌拳》3D 动作覆盖 · 战斗整帧对照（含 HUD）",
            font=f26, fill=(240, 240, 242))
    for i, sid in enumerate(SCENES[:5]):
        x = 18 + (i % 3) * (LW + 12)
        y = 56 + (i // 3) * (LH + 30)
        im = Image.open(rows[sid]["live"]).convert("RGB").resize(
            (LW, LH), Image.LANCZOS)
        b2.paste(im, (x, y))
        d2.rectangle((x, y, x + LW, y + LH),
                     outline=(70, 74, 90), width=1)
        d2.text((x + 4, y + LH + 4),
                f"{LABELS[i]}  P:{rows[sid]['player_card']} "
                f"F:{rows[sid]['foe_card']}",
                font=f17, fill=(210, 214, 224))
    yy2 = 56 + 2 * (LH + 30)
    d2.rectangle((0, yy2, W2, yy2 + 64), fill=(14, 16, 21))
    d2.text((18, yy2 + 12),
            "整帧含随机发牌，sha 不跨进程比较；动作判据以双层 SubViewport "
            "原图的 card/frame 与像素差异为准。",
            font=f17, fill=(190, 198, 212))
    b2.save(OUT2)

    checks = {
        "board1_written": OUT1.is_file() and OUT1.stat().st_size > 50000,
        "board2_written": OUT2.is_file() and OUT2.stat().st_size > 50000,
        "board1_size": Image.open(OUT1).size == (W, H),
        "board2_size": Image.open(OUT2).size == (W2, H2),
        "all_sources_exist": all(
            Path(rows[s][f"{side}_sv"]).is_file()
            and Path(rows[s]["live"]).is_file()
            for s in SCENES for side in ("player", "foe")),
    }
    for k, v in checks.items():
        print("CHECK", k, v)
    print("MOTION_BOARD_OK" if all(checks.values())
          else "MOTION_BOARD_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
