"""低血量红框脉冲的逐帧取证（阳性 7 帧 vs 阴性 7 帧）。

阳性 = 临时把 `r < 0.3` 变异成 `r < 2.0`，满血也进危险态；
阴性 = 逐字节还原后的正式 V2，同 7 个时间点。
7 点间隔 0.12s，覆盖 sin(t*9) 的一个完整周期（2π/9≈0.698s）。

对每帧取「纯边框行」y=42/43/69 的平均 R（这三行不与填充重叠，
已由 hud_danger_evidence.py 逐行核对过），以阴性帧为底色反推红框 alpha：

    R_out = (1-a)*R_base + a*R_red        R_red = 0.98*255 ≈ 250
    a = (R_out - R_base) / (250 - R_base)

修复后的公式是 0.55 + 0.25*sin(...)，理论范围 0.30..0.80。
验收：7 帧里反推 alpha 的最小值 >= 0.28（留一点量化误差）。

同时输出一张「最暗帧 vs 阴性帧」的放大对照图作为肉眼证据。
"""

from pathlib import Path

from PIL import Image, ImageDraw

MUT_DIR = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-hud-pulse-mutant")
NOR_DIR = Path(r"C:\Users\tutic\AppData\Local\Temp\cardboxer-hud-pulse-normal")
OUTDIR = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer-bake\背景图候选")
COMPARE = OUTDIR / "血条-低血量危险态-谷值对照.png"

TIMES = [4.60, 4.72, 4.84, 4.96, 5.08, 5.20, 5.32]
BARS = {"player": 44, "enemy": 784}
W = 452
BORDER_ROWS = (42, 43, 69)
R_RED = 0.98 * 255


def border_r(img: Image.Image, x0: int) -> float:
    px = img.load()
    vals = [px[x, y][0] for y in BORDER_ROWS for x in range(x0 + 20, x0 + W - 20)]
    return sum(vals) / len(vals)


def main() -> None:
    alphas: list[float] = []
    print(f"{'t':>6} {'base_R':>8} {'mut_R':>8} {'alpha':>7}  (enemy 纯边框行)")
    for i, t in enumerate(TIMES, start=1):
        nor = Image.open(NOR_DIR / f"shot_{i:02d}.png").convert("RGB")
        mut = Image.open(MUT_DIR / f"shot_{i:02d}.png").convert("RGB")
        base = border_r(nor, BARS["enemy"])
        out = border_r(mut, BARS["enemy"])
        a = (out - base) / (R_RED - base)
        alphas.append(a)
        print(f"{t:6.2f} {base:8.2f} {out:8.2f} {a:7.3f}")

    lo = min(alphas)
    hi = max(alphas)
    print(f"\nalpha min={lo:.3f} max={hi:.3f} mean={sum(alphas) / len(alphas):.3f}")
    print(f"理论范围 0.300..0.800；验收 min >= 0.280 -> {'PASS' if lo >= 0.28 else 'FAIL'}")

    # 最暗帧的放大对照：上=阴性正常态，下=阳性危险态（谷值）
    darkest = alphas.index(lo) + 1
    print(f"最暗帧 = shot_{darkest:02d} (t={TIMES[darkest - 1]:.2f})")
    crops = [(30, 25, 510, 90), (770, 25, 1250, 90)]
    scale = 2
    cw, ch = 480 * scale, 65 * scale
    canvas = Image.new("RGB", (cw * 2 + 20, ch * 2 + 60), (18, 18, 24))
    draw = ImageDraw.Draw(canvas)
    for row, (label, img) in enumerate([
        ("NORMAL  r < 0.3  (no danger)", Image.open(NOR_DIR / f"shot_{darkest:02d}.png").convert("RGB")),
        (f"DANGER  darkest frame  alpha={lo:.2f}", Image.open(MUT_DIR / f"shot_{darkest:02d}.png").convert("RGB")),
    ]):
        y_off = row * (ch + 30)
        draw.text((6, y_off + 4), label, fill=(235, 235, 240))
        for col, box in enumerate(crops):
            canvas.paste(img.crop(box).resize((cw, ch), Image.LANCZOS), (col * (cw + 20), y_off + 20))
    canvas.save(COMPARE)
    print(f"compare image -> {COMPARE}")

    # 顺带给出填充中心的危险色插值证据
    # 阴性帧在 5.32s 时对手已掉到 90%。只取「90% 与 100% 填充都必然覆盖」
    # 的区间，避免把空槽算进平均色。player 从左填、enemy 从右填(mirrored)。
    safe = {"player": (20, 400), "enemy": (60, 440)}
    px_n = Image.open(NOR_DIR / f"shot_{darkest:02d}.png").convert("RGB").load()
    px_m = Image.open(MUT_DIR / f"shot_{darkest:02d}.png").convert("RGB").load()
    for name, x0 in BARS.items():
        lo_x, hi_x = safe[name]
        n = [px_n[x0 + x, 56][:3] for x in range(lo_x, hi_x)]
        m = [px_m[x0 + x, 56][:3] for x in range(lo_x, hi_x)]
        avg = lambda s: tuple(sum(c[k] for c in s) // len(s) for k in range(3))
        print(f"fill center [{name}]: normal={avg(n)} danger={avg(m)}")


if __name__ == "__main__":
    main()
