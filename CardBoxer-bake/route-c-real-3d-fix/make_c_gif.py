"""C 路线：拼真 3D 网格攻击 GIF + 与上一轮 puppet / 旧网格的三方对照板。

沿用 3d-attack-gifs 的口径：取景框按全帧 alpha 并集自动算，
optimize=False + 总播放时长守恒（Pillow 会合并相同帧并累加 duration）。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
OLD = BAKE / "3d-attack-gifs"
GAME = BAKE.parent / "CardBoxer"
MOTION = json.loads((GAME / "data/card_motion.json").read_text(encoding="utf-8"))
REPORT = json.loads((HERE / "c_build.json").read_text(encoding="utf-8"))
IDS = ["jab", "cross", "wave"]
LABELS = {"jab": "散牌 · 刺拳", "cross": "三连 · 交叉反击", "wave": "三同 · 气功波"}
EXPECT = {"jab": 14, "cross": 22, "wave": 36}
FRAME_MS, PAD = 60, 30
BG, PANEL = (38, 42, 56), (42, 47, 62)


def font(size):
    for p in (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


FH, FL, FS = font(25), font(19), font(15)


def strip_files(cid):
    d = HERE / "frames"
    return sorted(d.glob(f"c-{cid}-f*.png"),
                  key=lambda p: int(re.search(r"f(\d+)", p.stem).group(1)))


def alpha_bbox(p):
    return Image.open(p).convert("RGBA").getchannel("A").getbbox()


def load_rgb(path, box=None):
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, BG + (255,))
    bg.alpha_composite(im)
    out = bg.convert("RGB")
    return out.crop(box) if box else out


def unified_box():
    boxes = [alpha_bbox(p) for cid in IDS for p in strip_files(cid)]
    boxes += [alpha_bbox(HERE / "frames" / "c-rest-unposed.png")]
    boxes = [b for b in boxes if b]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    side = max(x1 - x0, y1 - y0) + 2 * PAD
    W, H = Image.open(HERE / "frames" / "c-rest-unposed.png").size
    bx, by = max(0, min(W - 1, int(cx - side / 2))), max(0, min(H - 1, int(cy - side / 2)))
    actual = min(side, W - bx, H - by)
    return (bx, by, bx + actual, by + actual), (x0, y0, x1, y1)


def save_gif(frames, out, duration=FRAME_MS):
    pal = frames[0].quantize(colors=160, method=Image.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    q[0].save(out, save_all=True, append_images=q[1:], duration=duration,
              loop=0, optimize=False, disposal=1)
    im = Image.open(out)
    total = sum((im.seek(i) or im.info.get("duration", 0)) for i in range(im.n_frames))
    return {"file": out.name, "bytes": out.stat().st_size,
            "encoded_frames": im.n_frames, "duration_sum_ms": total,
            "expected_duration_ms": len(frames) * duration,
            "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}


def keyframe_sheet(by_card, out, title):
    CELL, GAP, MARGIN, HEAD, LABEL = 220, 10, 24, 78, 34
    ROW_H = LABEL + CELL + 30
    sheet = Image.new("RGB", (MARGIN * 2 + 4 * CELL + 3 * GAP,
                              HEAD + 3 * ROW_H), (28, 31, 42))
    d = ImageDraw.Draw(sheet)
    d.text((MARGIN, 20), title, font=FH, fill=(236, 240, 250))
    for r, cid in enumerate(IDS):
        top = HEAD + r * ROW_H
        frames, n = by_card[cid], len(by_card[cid])
        split = MOTION["cards"][cid]["split"]
        d.text((MARGIN, top), f"{LABELS[cid]}   {n} 帧 · 前摇/命中/收招 {split}",
               font=FL, fill=(240, 214, 160))
        for c, idx in enumerate([0, round(n / 3), round(2 * n / 3), n - 1]):
            x = MARGIN + c * (CELL + GAP)
            sheet.paste(frames[idx].resize((CELL, CELL), Image.LANCZOS),
                        (x, top + LABEL))
            phase = "前摇" if idx < split[0] else (
                "命中" if idx < split[0] + split[1] else "收招")
            d.text((x + 4, top + LABEL + CELL + 4), f"#{idx + 1:02d} {phase}",
                   font=FS, fill=(168, 180, 202))
    sheet.save(out)
    return {"file": out.name, "bytes": out.stat().st_size,
            "size": list(sheet.size)}


def three_way_board(box):
    """玩家 puppet / 对手怪 puppet / 对手怪真 3D 网格(C) / 旧网格(证伪)。"""
    CELL, GAP, MARGIN, HEAD, COLW = 240, 12, 24, 82, 240
    COLS = 4
    W = MARGIN * 2 + COLS * COLW + (COLS - 1) * GAP
    H = HEAD + 3 * (CELL + 40)
    board = Image.new("RGB", (W, H), (26, 29, 40))
    d = ImageDraw.Draw(board)
    d.text((MARGIN, 14), "C 路线前后对照 · 三档攻击命中帧", font=FH,
           fill=(236, 240, 250))
    heads = ["玩家 V4b / puppet", "对手怪 V1 / puppet",
             "对手怪 V1 / 真3D网格 C", "对手怪 V1 / 旧刚性网格"]
    for c, t in enumerate(heads):
        d.text((MARGIN + c * (COLW + GAP), 50), t, font=FS,
               fill=(240, 214, 160) if c == 2 else (168, 180, 202))

    old_stats = json.loads((OLD / "gif_stats.json").read_text(encoding="utf-8"))
    for r, cid in enumerate(IDS):
        n = EXPECT[cid]
        idx = round(n / 2)
        top = HEAD + r * (CELL + 40)
        cands = [
            (OLD / "frames" / "puppet_player", f"{cid}_f{idx:03d}.png",
             tuple(old_stats["routes"]["player"]["box"])),
            (OLD / "frames" / "puppet_foe", f"{cid}_f{idx:03d}.png",
             tuple(old_stats["routes"]["foe"]["box"])),
            (HERE / "frames", f"c-{cid}-f{idx:03d}.png", box),
            (OLD / "frames" / "foe", f"{cid}_f{idx:03d}.png",
             tuple(old_stats["routes"]["mesh"]["box"])),
        ]
        for c, (folder, fn, crop) in enumerate(cands):
            p = folder / fn
            assert p.is_file(), f"missing {p}"
            im = load_rgb(p, crop).resize((CELL, CELL), Image.LANCZOS)
            x = MARGIN + c * (COLW + GAP)
            board.paste(im, (x, top))
            d.text((x + 2, top + CELL + 4), f"{LABELS[cid]}  #{idx + 1:02d}",
                   font=FS, fill=(168, 180, 202))
    out = HERE / "C-route-four-way-comparison-board.png"
    board.save(out)
    return {"file": out.name, "bytes": out.stat().st_size,
            "size": list(board.size)}


def main():
    box, union = unified_box()
    print(f"BOX {box} alpha_union={union}", flush=True)
    by_card = {cid: [load_rgb(p, box) for p in strip_files(cid)] for cid in IDS}
    for cid in IDS:
        assert len(by_card[cid]) == EXPECT[cid], (cid, len(by_card[cid]))
    size = by_card["jab"][0].size
    assert all(im.size == size for fs in by_card.values() for im in fs)

    stats = {"box": list(box), "alpha_union": list(union), "gif_size": list(size),
             "frame_ms": FRAME_MS, "cards": {}}
    for cid in IDS:
        out = HERE / f"真3D网格-攻击-{cid}.gif"
        rec = save_gif(by_card[cid], out)
        assert rec["duration_sum_ms"] == rec["expected_duration_ms"], rec
        rec.update({"frames": len(by_card[cid]),
                    "split": MOTION["cards"][cid]["split"],
                    "merged_duplicate_frames": len(by_card[cid]) - rec["encoded_frames"]})
        stats["cards"][cid] = rec
        print(f"GIF {rec['file']} src={len(by_card[cid])} "
              f"enc={rec['encoded_frames']} duration={rec['duration_sum_ms']}ms "
              f"bytes={rec['bytes']}", flush=True)

    combo = []
    for cid in IDS:
        card = Image.new("RGB", size, (20, 23, 33))
        dc = ImageDraw.Draw(card)
        dc.text((size[0] // 2, size[1] // 2 - 22), LABELS[cid], font=FH,
                fill=(240, 214, 160), anchor="mm")
        dc.text((size[0] // 2, size[1] // 2 + 22),
                f"{len(by_card[cid])} 帧 · {MOTION['cards'][cid]['split']}",
                font=FL, fill=(150, 160, 180), anchor="mm")
        combo.extend([card, card])
        combo.extend(by_card[cid])
    stats["combo"] = save_gif(combo, HERE / "real-3d-mesh-three-level-loop.gif", FRAME_MS + 10)
    stats["combo"]["frames"] = len(combo)
    assert stats["combo"]["duration_sum_ms"] == stats["combo"]["expected_duration_ms"]

    stats["sheet"] = keyframe_sheet(
        by_card, HERE / "real-3d-mesh-keyframe-comparison.png",
        "C 路线 · 真 3D 网格 + 连续壳平滑权重 · 三档攻击关键帧")
    stats["board"] = three_way_board(box)
    (HERE / "c_gif_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print("C_GIF_OK", flush=True)


if __name__ == "__main__":
    main()
