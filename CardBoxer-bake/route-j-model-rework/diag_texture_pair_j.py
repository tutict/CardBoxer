"""J 路线 P0b：把两侧 baseColor 贴图缩略并排，判断画面里的白衫青云纹
到底来自哪张贴图。

若 foe 贴图整体是暗灰重装、没有大面积纯白下摆，而游戏截帧里 foe 侧
却有纯白长条 + 青色云纹，则「两人看起来同源」不是造型同源，而是
渲染/贴图串了——这时重做造型完全不对症。

只读，输出 boards/J-both-base-colors-comparison.png 与 data/texture_pair_j.json。
用法：python diag_texture_pair_j.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
BOARD = HERE / "boards" / "J-both-base-colors-comparison.png"
OUT = HERE / "data" / "texture_pair_j.json"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
NAMES = {
    "player": "player-rigged_texture_pbr_20250901.png",
    "foe": "foe-rigged_texture_pbr_20250901.png",
}


def main() -> int:
    imgs = {}
    for k, name in NAMES.items():
        p = GAME / "assets" / "3d" / name
        imgs[k] = Image.open(p).convert("RGB")

    size = (512, 512)
    pad, label = 20, 40
    canvas = Image.new("RGB", (2 * size[0] + 3 * pad,
                               size[1] + 2 * pad + label), (24, 28, 38))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 20) if FONT.is_file() \
        else ImageFont.load_default()
    stats = {}
    for i, k in enumerate(("player", "foe")):
        im = imgs[k]
        small = im.resize(size, Image.LANCZOS)
        x = pad + i * (size[0] + pad)
        canvas.paste(small, (x, pad))
        d.text((x + 4, pad + size[1] + 6),
               f"{k} · {NAMES[k]} · {im.size}", font=f,
               fill=(190, 200, 220))
        # 贴图里的近白像素占比：白衫下摆是否存在于这张贴图里。
        px = list(small.get_flattened_data())
        near_white = sum(1 for r, g, b in px
                         if r > 200 and g > 200 and b > 200)
        cyan = sum(1 for r, g, b in px
                   if b > 120 and g > 120 and r < g - 20)
        stats[k] = {
            "orig_size": list(im.size),
            "mean_rgb": [round(v, 2) for v in ImageStat.Stat(small).mean],
            "near_white_ratio_512": round(near_white / len(px), 5),
            "cyan_ratio_512": round(cyan / len(px), 5),
        }
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)
    checks = {
        "both_4096": all(v["orig_size"] == [4096, 4096]
                         for v in stats.values()),
        "foe_darker_than_player": (
            sum(stats["foe"]["mean_rgb"])
            < sum(stats["player"]["mean_rgb"]) - 150),
        "board_written": BOARD.is_file()
                         and BOARD.stat().st_size > 100000,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "board": str(BOARD), "board_bytes": BOARD.stat().st_size,
        "stats": stats, "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for k, v in stats.items():
        print("TEX", k, v)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("TEXTURE_PAIR_J_OK" if all(checks.values())
          else "TEXTURE_PAIR_J_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
