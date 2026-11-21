"""生成 B 路线 P0 真因对照板：同一进程 World3D 共享 → 独立的四帧。

输出 boards/B-World3D真因对照.png
用法：python make_truth_board.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "world3d"
SINGLE = HERE / "shots" / "single"
DATA = HERE / "data" / "world3d_probe.json"
BOARD = HERE / "boards" / "B-World3D真因对照.png"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")

CELLS = [
    ("w3d-before-sv-player.png", "现状 · player 视口",
     "两个角色叠在一起"),
    ("w3d-before-sv-foe.png", "现状 · foe 视口",
     "两个角色叠在一起"),
    ("w3d-after-sv-player.png", "独立 World3D · player 视口",
     "只剩白衫少女"),
    ("w3d-after-sv-foe.png", "独立 World3D · foe 视口",
     "只剩重甲怪"),
]


def main() -> int:
    report = json.loads(DATA.read_text(encoding="utf-8"))
    states = {s["tag"]: {r["label"]: r for r in s["layers"]}
              for s in report["payload"]["states"]}
    cw, ch, pad, lab, footer = 340, 421, 18, 62, 190
    W = 2 * cw + 3 * pad
    H = 2 * (ch + lab) + 3 * pad + footer
    canvas = Image.new("RGB", (W, H), (22, 26, 36))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 17) if FONT.is_file() \
        else ImageFont.load_default()
    fs = ImageFont.truetype(str(FONT), 15) if FONT.is_file() \
        else ImageFont.load_default()
    for i, (name, title, note) in enumerate(CELLS):
        col, row = i % 2, i // 2
        x = pad + col * (cw + pad)
        y = pad + row * (ch + lab + pad)
        im = Image.open(SHOTS / name).convert("RGBA")
        bg = Image.new("RGBA", im.size, (236, 239, 247, 255))
        bg.alpha_composite(im)
        canvas.paste(bg.convert("RGB").resize((cw, ch), Image.LANCZOS),
                     (x, y))
        d.text((x, y + ch + 4), title, font=f, fill=(222, 230, 244))
        d.text((x, y + ch + 27), note, font=fs, fill=(120, 215, 220))
        tag = "before" if i < 2 else "after"
        role = "player" if i % 2 == 0 else "foe"
        r = states[tag][role]["pixels"]
        d.text((x, y + ch + 45),
               f"近白 {r['near_white_px']}  青 {r['cyan_px']}  "
               f"占比 {r['white_ratio']:.1%}", font=fs,
               fill=(166, 178, 200))

    y0 = 2 * (ch + lab) + 3 * pad
    lines = [
        ("真因：两个 SubViewport 未设 own_world_3d（world_3d=null），",
         (240, 196, 120)),
        ("　　　共用父 World3D，每个视口都画进了两个角色。",
         (240, 196, 120)),
        ("各设独立 World3D 后：foe 视口近白 14,643 → 937，",
         (200, 212, 230)),
        ("　　　player 视口 17,602 → 13,197，与单层探针吻合。",
         (200, 212, 230)),
        ("结论：接线层 bug（fighter_3d_layer.gd::setup 一行），",
         (200, 212, 230)),
        ("　　　不是 GLB 叠层；J/B 删壳路线方向错误。",
         (200, 212, 230)),
        ("本轮 P0 只读取证，游戏源码 / GLB / 贴图零改动；修复待确认。",
         (150, 162, 184)),
    ]
    for i, (text, color) in enumerate(lines):
        d.text((pad, y0 + i * 23), text, font=fs, fill=color)
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)
    print("BOARD", BOARD, BOARD.stat().st_size, "bytes")
    print("TRUTH_BOARD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
