"""低血量分支的像素取证：正常版 vs 恒真变异版（满血同一时刻）。

几何（来自 hud.gd）：
  BAR_W=452, BAR_H=24；左条 pos=(44,44)，右条 pos=(784,44)。
  填充 Rect2(pos, 452x24) 覆盖 y=44..67。
  红框 Rect2(pos-1, 454x26) 覆盖 y=43..68，width=2，且**最后绘制**。
  所以 y=43 与 y=68 是纯边框行，不会被琥珀/青色填充污染，
  用它们数「红色像素」才能证明红框真的画出来了。

同时取填充中心 y=56 的平均色，证明 `lerp(HP_DANGER, pulse)` 生效。
"""

from pathlib import Path

from PIL import Image, ImageDraw

NORMAL = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-hud-shots\shot_01.png")
MUTANT = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-hud-danger\shot_01.png")
OUTDIR = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-hud-danger")
COMPARE = OUTDIR / "hud_compare.png"

BARS = {"player": 44, "enemy": 784}
W = 452


def is_red(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r > 120 and r - g > 55 and r - b > 55


def row_stats(img: Image.Image, x0: int, y: int) -> tuple[int, tuple[int, int, int]]:
    """逐行统计，避免把「填充行」误当「边框行」而得出假结论。"""
    px = img.load()
    samples = [px[x, y][:3] for x in range(x0 + 20, x0 + W - 20)]
    red = sum(1 for c in samples if is_red(c))
    avg = tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))
    return red, avg


def fill_avg(img: Image.Image, x0: int) -> tuple[int, int, int]:
    px = img.load()
    samples = [px[x, 56][:3] for x in range(x0 + 20, x0 + W - 20)]
    return tuple(sum(c[i] for c in samples) // len(samples) for i in range(3))


def main() -> None:
    normal = Image.open(NORMAL).convert("RGB")
    mutant = Image.open(MUTANT).convert("RGB")
    print(f"image size: normal={normal.size} mutant={mutant.size}")

    for name, x0 in BARS.items():
        print(f"\n[{name}] 逐行对照 (red_px / avg_rgb), normal -> mutant")
        for y in (42, 43, 44, 56, 67, 68, 69):
            nr, na = row_stats(normal, x0, y)
            mr, ma = row_stats(mutant, x0, y)
            delta = tuple(ma[i] - na[i] for i in range(3))
            print(f"  y={y:2d}  red {nr:3d}->{mr:3d} ({mr - nr:+4d})  {na} -> {ma}  delta={delta}")

    # 局部放大对照：左条 (30,25)-(510,90)，右条 (770,25)-(1250,90)，各 2x
    crops = [(30, 25, 510, 90), (770, 25, 1250, 90)]
    scale = 2
    cw = (510 - 30) * scale
    ch = (90 - 25) * scale
    canvas = Image.new("RGB", (cw * 2 + 20, ch * 2 + 60), (18, 18, 24))
    draw = ImageDraw.Draw(canvas)
    for row, (label, img) in enumerate([("NORMAL (r < 0.3)", normal), ("MUTANT (r < 2.0)", mutant)]):
        y_off = row * (ch + 30)
        draw.text((6, y_off + 4), label, fill=(235, 235, 240))
        for col, box in enumerate(crops):
            piece = img.crop(box).resize((cw, ch), Image.LANCZOS)
            canvas.paste(piece, (col * (cw + 20), y_off + 20))
    canvas.save(COMPARE)
    print(f"\ncompare image -> {COMPARE} size={canvas.size}")


if __name__ == "__main__":
    main()
