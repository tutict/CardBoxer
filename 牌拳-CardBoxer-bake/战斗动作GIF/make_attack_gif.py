"""把三条引擎内逐帧胶片拼成 GIF + 关键帧对照板 + 三档连播合辑。

取景框由「所有帧的亮像素联合包围盒」自动算出并统一使用，
三条 GIF 因此同尺度、同机位，可以直接对照；不靠目测写死坐标。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
MOTION = json.loads((GAME / "data/card_motion.json").read_text(encoding="utf-8"))
IDS = ["jab", "cross", "wave"]
LABELS = {"jab": "散牌 · 刺拳", "cross": "三连 · 交叉反击", "wave": "三同 · 气功波"}
BRIGHT = 60          # 亮度阈值：排除深蓝背景与身后暗圆，只留角色
PAD = 36
UPSCALE = 2
FRAME_MS = 60        # 比真实 60fps 慢一点，便于肉眼读动作


def font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_H, F_L, F_S = font(26), font(20), font(16)


def strip_files(cid):
    d = HERE / "frames" / cid
    return sorted(d.glob("strip_*.png"),
                  key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))


def bright_bbox(im):
    mask = im.convert("L").point(lambda v: 255 if v > BRIGHT else 0)
    return mask.getbbox()


raw = {cid: [Image.open(p).convert("RGB") for p in strip_files(cid)] for cid in IDS}
assert all(raw.values()), "empty strip"
W, H = raw["jab"][0].size
boxes = [bright_bbox(im) for frames in raw.values() for im in frames]
boxes = [b for b in boxes if b]
assert boxes, "no bright pixels found"
x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
side = max(x1 - x0, y1 - y0) + 2 * PAD
box = (max(0, int(cx - side / 2)), max(0, int(cy - side / 2)),
       min(W, int(cx + side / 2)), min(H, int(cy + side / 2)))
# 统一成正方形，避免三条 GIF 尺寸不同
side_actual = min(box[2] - box[0], box[3] - box[1])
box = (box[0], box[1], box[0] + side_actual, box[1] + side_actual)
print(f"UNIFIED_BOX {box} side={side_actual} bbox_all=({x0},{y0},{x1},{y1})", flush=True)

size = (side_actual * UPSCALE, side_actual * UPSCALE)
cropped = {}
for cid, frames in raw.items():
    cropped[cid] = [im.crop(box).resize(size, Image.LANCZOS) for im in frames]


def save_gif(frames, out, duration=FRAME_MS):
    pal = frames[0].quantize(colors=160, method=Image.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=duration,
              loop=0, optimize=True, disposal=1)
    return out.stat().st_size


stats = {"unified_box": list(box), "gif_size": list(size), "frame_ms": FRAME_MS,
         "bright_threshold": BRIGHT, "cards": {}}
for cid in IDS:
    out = HERE / f"攻击-{cid}.gif"
    n = len(cropped[cid])
    b = save_gif(cropped[cid], out)
    split = MOTION["cards"][cid]["split"]
    stats["cards"][cid] = {"frames": n, "split": split, "gif_bytes": b,
                           "label": LABELS[cid], "file": out.name}
    print(f"GIF {cid} frames={n} split={split} bytes={b}", flush=True)

# --- 关键帧对照板：每条取 4 帧，标相位 ----------------------------------
COLS = 4
CELL, GAP = 240, 10
MARGIN, HEAD, ROW_H = 24, 104, CELL + 82
sheet = Image.new("RGB",
                  (MARGIN * 2 + COLS * CELL + (COLS - 1) * GAP,
                   HEAD + len(IDS) * ROW_H),
                  (247, 248, 250))
ds = ImageDraw.Draw(sheet)
ds.text((MARGIN, 22), "《牌拳》回合制赢家攻击 · 三档动作关键帧（引擎内真实渲染）",
        font=F_H, fill=(31, 36, 48))
for r, cid in enumerate(IDS):
    top = HEAD + r * ROW_H
    n = len(cropped[cid])
    split = MOTION["cards"][cid]["split"]
    picks = [0, round(n / 3), round(2 * n / 3), n - 1]
    # 行标签放在自己这一行的顶部留白里，不压上一行的帧号
    ds.text((MARGIN, top - 34), f"{LABELS[cid]}   {n} 帧 · 前摇/命中/收招 {split}",
            font=F_L, fill=(31, 36, 48))
    for c, idx in enumerate(picks):
        im = cropped[cid][idx].resize((CELL, CELL), Image.LANCZOS)
        x = MARGIN + c * (CELL + GAP)
        sheet.paste(im, (x, top))
        phase = "前摇" if idx < split[0] else (
            "命中" if idx < split[0] + split[1] else "收招")
        ds.text((x + 6, top + CELL + 6), f"#{idx + 1:02d} {phase}",
                font=F_S, fill=(92, 100, 116))
sheet_path = HERE / "三档攻击-关键帧对照.png"
sheet.save(sheet_path)

# --- 三档连播合辑：每段前加一帧标题卡 ------------------------------------
title_w, title_h = size[0], size[1]
combo = []
for cid in IDS:
    card = Image.new("RGB", size, (18, 20, 30))
    dc = ImageDraw.Draw(card)
    dc.text((size[0] // 2, size[1] // 2 - 20), LABELS[cid],
            font=F_H, fill=(240, 220, 170), anchor="mm")
    dc.text((size[0] // 2, size[1] // 2 + 24),
            f"{len(cropped[cid])} 帧 · {MOTION['cards'][cid]['split']}",
            font=F_L, fill=(150, 160, 180), anchor="mm")
    combo.extend([card, card])
    combo.extend(cropped[cid])
combo_out = HERE / "三档攻击-连播.gif"
combo_bytes = save_gif(combo, combo_out, duration=FRAME_MS + 10)
print(f"COMBO frames={len(combo)} bytes={combo_bytes}", flush=True)

stats["sheet"] = {"file": sheet_path.name, "bytes": sheet_path.stat().st_size,
                  "size": list(sheet.size)}
stats["combo"] = {"file": combo_out.name, "frames": len(combo),
                  "bytes": combo_bytes}
(HERE / "gif_stats.json").write_text(
    json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
print("ATTACK_GIF_OK", flush=True)
