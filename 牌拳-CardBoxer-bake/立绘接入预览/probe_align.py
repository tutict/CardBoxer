"""只读探针：1) 定位截帧里两个火柴人的像素包围盒；2) 验证背景图能否当"橡皮"用。

合成 A 要擦掉火柴人，最干净的做法是从游戏背景原图取同一区域盖回去。
只有当背景图与引擎截帧在角色区域之外逐像素对齐时，这个做法才成立。
"""
from pathlib import Path
from PIL import Image, ImageChops
import statistics

BAKE = Path(__file__).resolve().parent.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
SHOT = BAKE / "背景图候选" / "怒火槽" / "怒火槽-满槽.png"
BG_CANDIDATES = [
    GAME / "background" / "arena.png",
    BAKE / "背景图候选" / "mcp_template_sdxl.png",
    BAKE / "背景图候选" / "arena_bg_sdxl_dark_01.png",
]


def color_bbox(im, pred, region):
    xs, ys = [], []
    x0, y0, x1, y1 = region
    px = im.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if pred(r, g, b):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None, 0
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1), len(xs)


def orange(r, g, b):
    return r > 115 and r > g * 1.22 and g > b * 1.25 and b < 145


def cyan(r, g, b):
    return b > 130 and b > r * 1.25 and g > r * 1.10 and b >= g * 0.92


def main():
    out = []
    with Image.open(SHOT) as s:
        shot = s.convert("RGB")
    out.append(f"SHOT {SHOT.relative_to(BAKE)} size={shot.size}")

    pbox, pn = color_bbox(shot, orange, (200, 200, 630, 550))
    ebox, en = color_bbox(shot, cyan, (650, 200, 1090, 550))
    out.append(f"PLAYER orange bbox={pbox} px={pn}")
    out.append(f"ENEMY  cyan   bbox={ebox} px={en}")
    # 身体（不含脚下椭圆阴影）单独量一次，合成时只擦这一块
    pbody, pbn = color_bbox(shot, orange, (200, 280, 630, 500))
    ebody, ebn = color_bbox(shot, cyan, (650, 280, 1090, 500))
    out.append(f"PLAYER body_only bbox={pbody} px={pbn}")
    out.append(f"ENEMY  body_only bbox={ebody} px={ebn}")

    for p in BG_CANDIDATES:
        if not p.exists():
            out.append(f"BG MISSING {p}")
            continue
        with Image.open(p) as b:
            bg = b.convert("RGB")
        out.append(f"BG {p.name} @ {p.parent.name} size={bg.size}")
        if bg.size != shot.size:
            bg = bg.resize(shot.size, Image.LANCZOS)
            out.append("  (resized to shot size for comparison)")
        # 在角色区之外采样：左右边带 + 擂台上沿 + 中间空档
        regions = [
            (0, 200, 180, 500),
            (1090, 200, 1280, 500),
            (560, 250, 700, 320),
            (0, 120, 1280, 160),
        ]
        diffs, equal, total = [], 0, 0
        for reg in regions:
            a = shot.crop(reg)
            c = bg.crop(reg)
            d = ImageChops.difference(a, c)
            for v in d.convert("L").getdata():
                diffs.append(v)
                total += 1
                if v == 0:
                    equal += 1
        out.append(
            f"  bg-vs-shot mean_abs_diff={statistics.mean(diffs):.3f} "
            f"max={max(diffs)} exact_equal={equal}/{total} ({equal / total:.4f})"
        )

    text = "\n".join(out) + "\n"
    (Path(__file__).resolve().parent / "probe_align.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
