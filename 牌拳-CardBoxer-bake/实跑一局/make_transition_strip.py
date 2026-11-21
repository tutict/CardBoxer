"""B 路线 · 连续帧复核条带：把归零处 / 最大跳变处 / 亮牌平台段逐帧摊开。

时间线里 cap9 曲线呈方波（腿峰值整段钉在 9° 再陡降归零），单张
静态帧看不出是否「锁死」。这里按真实 idx 连续取 7 帧，玩家 / 对手
各一行，三组并排，供看图定性。

用法：python make_transition_strip.py
产出：boards/实跑一局-连续帧复核.png、data/transition_strip.json
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BOARDS = HERE / "boards"
D = HERE / "data"
LIVE = D / "live_match.json"
OUT_IMG = BOARDS / "实跑一局-连续帧复核.png"
OUT_JSON = D / "transition_strip.json"

GROUPS = [
    ("A 亮牌平台段 focus（idx 17-23）", list(range(17, 24))),
    ("B 玩家归零前后（idx 76-82，cap9 残差 5.26°）",
     list(range(76, 83))),
    ("C 对手最大跳变前后（idx 111-117，14.86°）",
     list(range(111, 118))),
]


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


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    rows = {r["idx"]: r for r in
            live["cases"]["cap9"]["payload"]["rows"]}
    CW, CH = 140, 174
    GAP, LEFT = 8, 128
    N = len(GROUPS[0][1])
    W = LEFT + N * (CW + GAP) + 16
    GROUP_H = 2 * (CH + 26) + 40
    H = 76 + len(GROUPS) * GROUP_H + 54
    im = gradient(W, H)
    d = ImageDraw.Draw(im)
    f22, f14, f12 = font(22), font(14), font(12)
    d.text((14, 10), "《牌拳》实跑一局 · 连续帧复核（cap9 落盘态）",
           font=f22, fill=(240, 240, 244))
    d.text((14, 42), "每格为引擎内 SubViewport 原图按真实 idx 顺序摊开；"
           "上排玩家，下排对手。", font=f14,
           fill=(190, 198, 212))
    present = 0
    for gi, (title, idxs) in enumerate(GROUPS):
        gy = 76 + gi * GROUP_H
        d.text((14, gy), title, font=f14, fill=(255, 214, 160))
        for ri, side in enumerate(("player", "foe")):
            y = gy + 22 + ri * (CH + 26)
            d.text((10, y + CH // 2 - 8),
                   "玩家" if side == "player" else "对手",
                   font=f14, fill=(190, 198, 212))
            for ci, idx in enumerate(idxs):
                x = LEFT + ci * (CW + GAP)
                r = rows.get(idx)
                p = r.get(f"{side}_sv") if r else ""
                if p and Path(p).is_file():
                    fg = Image.open(p).convert("RGBA")
                    bg = gradient(fg.width, fg.height).convert("RGBA")
                    bg.alpha_composite(fg)
                    pic = bg.convert("RGB").resize(
                        (CW, CH), Image.LANCZOS)
                    im.paste(pic, (x, y))
                    present += 1
                else:
                    d.rectangle((x, y, x + CW, y + CH),
                                fill=(40, 40, 50))
                d.rectangle((x, y, x + CW, y + CH),
                            outline=(70, 74, 90))
                card = r[f"{side}"]["card"] if r else "-"
                fr = r[f"{side}"]["frame"] if r else "-"
                d.text((x, y + CH + 3),
                       f"{idx} {card[:9]}:{fr}", font=f12,
                       fill=(205, 212, 224))
    d.text((14, H - 40),
           "判读重点：相邻格姿态是否渐变、切回 stance 前有无突然归零、"
           "腿是否整段固定外撇。", font=f14,
           fill=(170, 230, 190))
    im.save(OUT_IMG)
    checks = {
        "strip_written": OUT_IMG.is_file()
        and OUT_IMG.stat().st_size > 100000,
        "all_panels_present": present == len(GROUPS) * 2 * N,
        "three_groups": len(GROUPS) == 3,
        "seven_frames_each": all(len(v) == N for _, v in GROUPS),
    }
    OUT_JSON.write_text(json.dumps(
        {"present_panels": present,
         "expected_panels": len(GROUPS) * 2 * N,
         "groups": [{"title": t, "idx": v} for t, v in GROUPS],
         "size": im.size, "bytes": OUT_IMG.stat().st_size,
         "checks": checks, "ok": all(checks.values())},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PANELS", present, "/", len(GROUPS) * 2 * N)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("TRANSITION_STRIP_OK" if all(checks.values())
          else "TRANSITION_STRIP_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
