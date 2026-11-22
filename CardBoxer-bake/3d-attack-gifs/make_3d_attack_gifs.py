"""把 73 帧/角色/路线 拼成 GIF、关键帧板与总览对照板。

取景框按「所有帧 alpha 通道的联合包围盒」自动算，不写死坐标；
三条路线各自算，因为 puppet 是 768² 而真 3D 网格是 512²。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "CardBoxer"
MOTION = json.loads((GAME / "data/card_motion.json").read_text(encoding="utf-8"))
IDS = ["jab", "cross", "wave"]
LABELS = {"jab": "散牌 · 刺拳", "cross": "三连 · 交叉反击", "wave": "三同 · 气功波"}
BG = (38, 42, 56)
FG = (236, 240, 250)
MUTED = (168, 180, 202)
GOLD = (240, 214, 160)
FRAME_MS = 60
PAD = 30

ROUTES = [
    ("player", "puppet_player", "玩家 V4b · 3D 立绘骨骼 puppet", "玩家V4b"),
    ("foe", "puppet_foe", "对手怪 V1 · 3D 立绘骨骼 puppet", "对手怪V1"),
    ("mesh", "foe", "对手怪 V1 · 真 3D 网格驱动（证伪）", "证伪-网格"),
]


def font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_H, F_L, F_S = font(25), font(19), font(15)


def strip_files(folder, cid):
    return sorted(folder.glob(f"{cid}_f*.png"),
                  key=lambda p: int(re.search(r"f(\d+)", p.stem).group(1)))


def load_rgb(path):
    """透明 PNG -> 深色底 RGB，避免 GIF 调色板把 alpha 吃掉。"""
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, BG + (255,))
    bg.alpha_composite(im)
    return bg.convert("RGB")


def alpha_bbox(path):
    return Image.open(path).convert("RGBA").getchannel("A").getbbox()


def unified_box(folder):
    boxes = [alpha_bbox(p) for cid in IDS for p in strip_files(folder, cid)]
    boxes += [alpha_bbox(p) for p in folder.glob("stance_f*.png")]
    boxes = [b for b in boxes if b]
    assert boxes, f"no alpha in {folder}"
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = max(x1 - x0, y1 - y0) + 2 * PAD
    W, H = Image.open(next(folder.glob("stance_f*.png"))).size
    bx = max(0, min(W - 1, int(cx - side / 2)))
    by = max(0, min(H - 1, int(cy - side / 2)))
    actual = min(side, W - bx, H - by)
    return (bx, by, bx + actual, by + actual), (x0, y0, x1, y1)


def save_gif(frames, out, duration=FRAME_MS):
    pal = frames[0].quantize(colors=160, method=Image.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    # 实测订正：Pillow 的 GIF 写入会把像素完全相同的连续帧合并，并把被合并帧
    # 的时长累加到保留帧（jab 14 帧 -> 11 帧，但总时长仍是 14x60=840ms）。
    # optimize=True/False 都不改变这个行为；关掉帧间差分只是让每帧自包含全图，
    # 便于逐帧提取。判据因此查「总播放时长守恒」而不是「GIF 帧数相等」。
    q[0].save(out, save_all=True, append_images=q[1:], duration=duration,
              loop=0, optimize=False, disposal=1)
    im = Image.open(out)
    total_ms = sum((im.seek(i) or im.info.get("duration", 0))
                   for i in range(im.n_frames))
    return out.stat().st_size, im.n_frames, total_ms


def keyframe_sheet(frames_by_card, out_path, title):
    """3 行 x 4 帧；行标签放在自己这一行的顶部留白，不压上一行。"""
    CELL, GAP, MARGIN, HEAD, LABEL = 220, 10, 24, 78, 34
    ROW_H = LABEL + CELL + 30
    W = MARGIN * 2 + 4 * CELL + 3 * GAP
    sheet = Image.new("RGB", (W, HEAD + 3 * ROW_H), (28, 31, 42))
    d = ImageDraw.Draw(sheet)
    d.text((MARGIN, 20), title, font=F_H, fill=FG)
    for r, cid in enumerate(IDS):
        top = HEAD + r * ROW_H
        frames = frames_by_card[cid]
        n = len(frames)
        split = MOTION["cards"][cid]["split"]
        d.text((MARGIN, top), f"{LABELS[cid]}   {n} 帧 · 前摇/命中/收招 {split}",
               font=F_L, fill=GOLD)
        picks = [0, round(n / 3), round(2 * n / 3), n - 1]
        for c, idx in enumerate(picks):
            im = frames[idx].resize((CELL, CELL), Image.LANCZOS)
            x = MARGIN + c * (CELL + GAP)
            sheet.paste(im, (x, top + LABEL))
            phase = "前摇" if idx < split[0] else (
                "命中" if idx < split[0] + split[1] else "收招")
            d.text((x + 4, top + LABEL + CELL + 4), f"#{idx + 1:02d} {phase}",
                   font=F_S, fill=MUTED)
    sheet.save(out_path)
    return out_path.stat().st_size


def main():
    stats = {"frame_ms": FRAME_MS, "pad": PAD, "routes": {}}
    combo_frames = {}
    for key, folder_name, title, prefix in ROUTES:
        folder = HERE / "frames" / folder_name
        box, bbox_all = unified_box(folder)
        log_w, log_h = Image.open(next(folder.glob("stance_f*.png"))).size
        print(f"BOX {key}: {box} alpha_union={bbox_all} src={log_w}x{log_h}", flush=True)
        by_card = {}
        for cid in IDS:
            by_card[cid] = [load_rgb(p).crop(box) for p in strip_files(folder, cid)]
        size = by_card[IDS[0]][0].size
        assert all(im.size == size for frames in by_card.values() for im in frames)
        entry = {"box": list(box), "alpha_union": list(bbox_all),
                 "gif_size": list(size), "cards": {}}
        for cid in IDS:
            out = HERE / f"{prefix}-攻击-{cid}.gif"
            b, enc, ms = save_gif(by_card[cid], out)
            entry["cards"][cid] = {
                "frames": len(by_card[cid]), "split": MOTION["cards"][cid]["split"],
                "file": out.name, "bytes": b,
                "encoded_frames": enc, "merged_duplicate_frames": len(by_card[cid]) - enc,
                "duration_sum_ms": ms,
                "expected_duration_ms": len(by_card[cid]) * FRAME_MS,
                "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            }
            print(f"GIF {out.name} src={len(by_card[cid])} enc={enc} "
                  f"duration={ms}ms bytes={b}", flush=True)

        sheet = HERE / f"{prefix}-关键帧对照.png"
        entry["sheet"] = {"file": sheet.name,
                          "bytes": keyframe_sheet(by_card, sheet, title),
                          "size": list(Image.open(sheet).size)}

        # 三档连播：每段前插 2 帧标题卡
        combo = []
        for cid in IDS:
            card = Image.new("RGB", size, (20, 23, 33))
            dc = ImageDraw.Draw(card)
            dc.text((size[0] // 2, size[1] // 2 - 22), LABELS[cid],
                    font=F_H, fill=GOLD, anchor="mm")
            dc.text((size[0] // 2, size[1] // 2 + 22),
                    f"{len(by_card[cid])} 帧 · {MOTION['cards'][cid]['split']}",
                    font=F_L, fill=MUTED, anchor="mm")
            combo.extend([card, card])
            combo.extend(by_card[cid])
        combo_out = HERE / f"{prefix}-三档连播.gif"
        cb, cenc, cms = save_gif(combo, combo_out, FRAME_MS + 10)
        entry["combo"] = {"file": combo_out.name, "frames": len(combo),
                          "encoded_frames": cenc, "duration_sum_ms": cms,
                          "expected_duration_ms": len(combo) * (FRAME_MS + 10),
                          "bytes": cb,
                          "sha256": hashlib.sha256(combo_out.read_bytes()).hexdigest()}
        stats["routes"][key] = entry
        combo_frames[key] = combo

    # 总览：3 列（路线）x 3 行（档位命中帧）
    CELL, GAP, MARGIN, HEAD, COLW = 230, 14, 24, 76, 230
    W = MARGIN * 2 + 3 * COLW + 2 * GAP
    H = HEAD + 3 * (CELL + 44)
    board = Image.new("RGB", (W, H), (26, 29, 40))
    d = ImageDraw.Draw(board)
    d.text((MARGIN, 16), "新 3D 建模人物 · 三档攻击：三条驱动路线命中帧对照",
           font=F_H, fill=FG)
    for c, (key, _f, title, _p) in enumerate(ROUTES):
        short = ["玩家 V4b / puppet", "对手怪 V1 / puppet", "对手怪 V1 / 真3D网格"][c]
        d.text((MARGIN + c * (COLW + GAP), 50), short, font=F_S,
               fill=GOLD if c < 2 else (238, 138, 138))
    for r, cid in enumerate(IDS):
        top = HEAD + r * (CELL + 44)
        for c, key in enumerate(["player", "foe", "mesh"]):
            frames = stats["routes"][key]
            folder = HERE / "frames" / ROUTES[c][1]
            box = frames["box"]
            n = frames["cards"][cid]["frames"]
            idx = round(n / 2)
            p = strip_files(folder, cid)[idx]
            im = load_rgb(p).crop(box).resize((CELL, CELL), Image.LANCZOS)
            x = MARGIN + c * (COLW + GAP)
            board.paste(im, (x, top))
            d.text((x + 2, top + CELL + 4), f"{LABELS[cid]}  #{idx + 1:02d}",
                   font=F_S, fill=MUTED)
    board_path = HERE / "three-routes-impact-frame-overview.png"
    board.save(board_path)
    stats["overview"] = {"file": board_path.name, "bytes": board_path.stat().st_size,
                         "size": list(board.size)}
    (HERE / "gif_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ATTACK_3D_GIF_OK", flush=True)


if __name__ == "__main__":
    main()
