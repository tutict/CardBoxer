"""把引擎内 9 帧截帧整理成对照板，并落盘版面统计。

用法：python make_boards_f.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots"
BOARDS = HERE / "boards"
OUT = HERE / "data" / "board_stats_f.json"

BG = (17, 21, 31)
FG = (232, 236, 245)
SUB = (150, 162, 184)
ACC = (120, 214, 196)


def font(sz: int):
    for name in ("C:/Windows/Fonts/msyh.ttc",
                 "C:/Windows/Fonts/msyhbd.ttc",
                 "C:/Windows/Fonts/simhei.ttf"):
        p = Path(name)
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), sz)
            except OSError:
                pass
    return ImageFont.load_default()


def load(name: str) -> Image.Image:
    p = SHOTS / f"f-{name}.png"
    return Image.open(p).convert("RGB")


def thumb(name: str, w: int, h: int) -> Image.Image:
    return load(name).resize((w, h), Image.LANCZOS)


def main() -> int:
    BOARDS.mkdir(parents=True, exist_ok=True)
    f_title = font(34)
    f_sub = font(19)
    f_tag = font(17)
    made = []

    # 板 1：九帧总览 3x3
    tw, th = 300, 367
    pad, gap, top, bot = 28, 16, 112, 46
    W = pad * 2 + tw * 3 + gap * 2
    H = top + th * 3 + 34 * 3 + gap * 2 + bot
    b = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(b)
    d.text((pad, 22), "F 路线 · Godot 运行时 14 骨驱动层 · 引擎内九帧",
           font=f_title, fill=FG)
    d.text((pad, 68), "同一份 player-rigged.glb，同一条 main_scene；"
           "逐帧由 GDScript 现算 retarget，不播烘死动画",
           font=f_sub, fill=SUB)
    grid = [
        ("stance-front", "站架 / stance · yaw 0"),
        ("stance-front-repeat", "站架重渲 · 确定性样本"),
        ("jab06-front", "jab f6 · 21.39°"),
        ("cross07-front", "cross f7 · 28.00°"),
        ("wave17-front", "wave f17 · 13.57°"),
        ("wave35-front", "wave f35 · 收势"),
        ("jab06-angle35", "jab f6 · yaw 35°"),
        ("cross07-angle35", "cross f7 · yaw 35°"),
        ("wave17-angle35", "wave f17 · yaw 35°"),
    ]
    for i, (name, label) in enumerate(grid):
        r, c = divmod(i, 3)
        x = pad + c * (tw + gap)
        y = top + r * (th + 34 + gap)
        b.paste(thumb(name, tw, th), (x, y))
        d.rectangle((x, y, x + tw, y + th), outline=(70, 80, 100), width=1)
        d.text((x + 2, y + th + 6), label, font=f_tag, fill=ACC)
    p1 = BOARDS / "F-九帧动作总览.png"
    b.save(p1)
    made.append({"name": p1.name, "bytes": p1.stat().st_size,
                 "w": b.width, "h": b.height, "cells": len(grid)})

    # 板 2：正视角四关键帧一排
    tw2, th2 = 360, 440
    pad2, gap2, top2 = 28, 18, 112
    W2 = pad2 * 2 + tw2 * 4 + gap2 * 3
    H2 = top2 + th2 + 96
    b2 = Image.new("RGB", (W2, H2), BG)
    d2 = ImageDraw.Draw(b2)
    d2.text((pad2, 22), "F 路线 · 站架 vs 三档攻击（引擎内正视）",
            font=f_title, fill=FG)
    d2.text((pad2, 68), "同一相机、同一灯光；差别只来自逐帧骨骼驱动",
            font=f_sub, fill=SUB)
    line = [
        ("stance-front", "stance / 站架", "root 0.00 m"),
        ("jab06-front", "jab f6 / 直拳", "root +0.13 m"),
        ("cross07-front", "cross f7 / 后手", "root +0.19 m"),
        ("wave17-front", "wave f17 / 双手", "root +0.09 m"),
    ]
    for i, (name, label, sub) in enumerate(line):
        x = pad2 + i * (tw2 + gap2)
        b2.paste(thumb(name, tw2, th2), (x, top2))
        d2.rectangle((x, top2, x + tw2, top2 + th2),
                     outline=(70, 80, 100), width=1)
        d2.text((x + 2, top2 + th2 + 8), label, font=f_tag, fill=ACC)
        d2.text((x + 2, top2 + th2 + 34), sub, font=f_tag, fill=SUB)
    p2 = BOARDS / "F-站架与三档攻击.png"
    b2.save(p2)
    made.append({"name": p2.name, "bytes": p2.stat().st_size,
                 "w": b2.width, "h": b2.height, "cells": len(line)})

    # 板 3：正/侧视角对照（体积证据）
    tw3, th3 = 330, 403
    pad3, gap3, top3 = 28, 20, 112
    W3 = pad3 * 2 + tw3 * 3 + gap3 * 2
    H3 = top3 + (th3 + 38) * 2 + 60
    b3 = Image.new("RGB", (W3, H3), BG)
    d3 = ImageDraw.Draw(b3)
    d3.text((pad3, 22), "F 路线 · 正视 / 35° 侧视对照",
            font=f_title, fill=FG)
    d3.text((pad3, 68), "侧视可见长衫、披肩与发束的真实厚度，不是纸片",
            font=f_sub, fill=SUB)
    pairs = [
        (0, ("jab06-front", "jab06-angle35"), "jab f6"),
        (1, ("cross07-front", "cross07-angle35"), "cross f7"),
        (2, ("wave17-front", "wave17-angle35"), "wave f17"),
    ]
    for c, (front, angle), label in pairs:
        x = pad3 + c * (tw3 + gap3)
        for r, nm in enumerate((front, angle)):
            y = top3 + r * (th3 + 38)
            b3.paste(thumb(nm, tw3, th3), (x, y))
            d3.rectangle((x, y, x + tw3, y + th3),
                         outline=(70, 80, 100), width=1)
            d3.text((x + 2, y + th3 + 6),
                    "%s · %s" % (label, "正视" if r == 0 else "35° 侧视"),
                    font=f_tag, fill=ACC)
    p3 = BOARDS / "F-正视与侧视体积.png"
    b3.save(p3)
    made.append({"name": p3.name, "bytes": p3.stat().st_size,
                 "w": b3.width, "h": b3.height, "cells": 6})

    # 板 4：四层数字成本账（纯文字）
    W4, H4 = 1180, 760
    b4 = Image.new("RGB", (W4, H4), BG)
    d4 = ImageDraw.Draw(b4)
    d4.text((36, 24), "F 路线 · 驱动链成本账与边界", font=f_title, fill=FG)
    rows = [
        ("资产", "player-rigged.glb  38,478,140 B",
         "57,934 顶点高模带 JOINTS_0/WEIGHTS_0；14 joints；0 animations"),
        ("导入", "Godot 4.5  Skeleton3D 14 骨",
         "player_HI_skinned  skeleton_path='..'  skin_present=true"),
        ("输入", "motion_input.json  19,771 B",
         "原始 2D 关节表 + retarget 参数，无任何烘死 pose / quat"),
        ("驱动", "RigDriver.gd  GDScript 现算",
         "make_points / angle / wrap_pi / retarget_delta / root 位移"),
        ("口径", "Godot (X,Y,Z) = Blender (x,z,-y)",
         "RotY(delta)_Blender == RotZ(-delta)_Godot"),
        ("对账", "73 帧 × 13 骨 × 三重",
         "delta 1e-5° / calc-engine 1e-6 m / engine-Blender 1e-6 m"),
        ("截帧", "引擎内 9 帧 900×1100  5.086 s",
         "重复帧字节相同；攻击帧 28–33 万像素变化"),
        ("边界", "可运行游戏工程 105 文件 0 drift",
         "游戏内 3D 资产 0；本工程是隔离探针，不是生产导入"),
        ("未解", "动作幅度偏小，仍像 A-pose 摆臂",
         "侧视 2D 动作表重定向到正视 A-pose 的固有语义损失"),
    ]
    y = 96
    for i, (k, v, note) in enumerate(rows):
        d4.rectangle((36, y - 6, W4 - 36, y + 62),
                     fill=(24, 29, 42) if i % 2 == 0 else (20, 25, 36))
        d4.text((52, y + 2), k, font=f_tag, fill=ACC)
        d4.text((148, y + 2), v, font=f_sub, fill=FG)
        d4.text((148, y + 30), note, font=f_tag, fill=SUB)
        y += 70
    p4 = BOARDS / "F-驱动链成本账.png"
    b4.save(p4)
    made.append({"name": p4.name, "bytes": p4.stat().st_size,
                 "w": b4.width, "h": b4.height, "rows": len(rows)})

    OUT.write_text(json.dumps({"boards": made, "count": len(made)},
                              ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for m in made:
        print(f"BOARD {m['name']:<28} {m['w']}x{m['h']} {m['bytes']} B")
    print("BOARDS_F_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
