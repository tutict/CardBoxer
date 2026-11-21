"""看图辅助：把 cross11 腰间区域裁出来，确认 V2 基线 / A2 重做的斜片差异。

只读 frames/ 与 C路线-变形质量V2/frames/，输出一张放大对照，不改原图。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
C2 = BAKE / "C路线-变形质量V2" / "frames"
F = HERE / "frames"
OUT = HERE / "A-腰间斜片特写.png"
STATS = HERE / "shard_stats.json"


def font(size):
    try:
        return ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", size)
    except OSError:
        return ImageFont.load_default()


def crop(p: Path, box):
    im = Image.open(p).convert("RGB")
    return im.crop(box)


def main() -> int:
    a = C2 / "cross11-B_x15.png"
    b = F / "a-cross11-x15.png"
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    assert ia.size == ib.size, (ia.size, ib.size)
    w, h = ia.size
    # 腰 / 髋区域：左右两腿之间到左髋外侧，斜片在 V2 基线里出现在这里
    box = (int(w * 0.30), int(h * 0.34), int(w * 0.62), int(h * 0.62))
    ca, cb = crop(a, box), crop(b, box)

    def bright_px(im):
        r, g, b = im.split()
        mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
        return mx.point(lambda v: 255 if v > 70 else 0).histogram()[255]

    pa, pb = bright_px(ca), bright_px(cb)
    zoom = 2
    cw, ch = ca.width * zoom, ca.height * zoom
    board = Image.new("RGB", (cw * 2 + 60, ch + 96), (20, 25, 36))
    board.paste(ca.resize((cw, ch), Image.Resampling.LANCZOS), (20, 60))
    board.paste(cb.resize((cw, ch), Image.Resampling.LANCZOS), (cw + 40, 60))
    d = ImageDraw.Draw(board)
    f = font(17)
    d.text((20, 18), "V2 定稿基线 cross11-B_x15（腰间斜片）", font=f,
           fill=(236, 240, 250))
    d.text((cw + 40, 18), "A2 重做后 a-cross11-x15", font=f,
           fill=(236, 240, 250))
    d.text((20, ch + 66), f"裁剪框 {box} / 亮像素 {pa} vs {pb} "
                          f"（阈值 RGB 最大值 > 70）", font=font(13),
           fill=(152, 164, 184))
    board.save(OUT)
    STATS.write_text(json.dumps({
        "source_size": list(ia.size), "box": list(box),
        "bright_pixels_v2": pa, "bright_pixels_a2": pb,
        "delta": pb - pa,
        "note": "亮像素数只用于定位裁剪框内的可见差异，不作为几何质量判据"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SHARD_CLOSEUP {OUT.name} bytes={OUT.stat().st_size} "
          f"bright_v2={pa} bright_a2={pb}")
    print("SHARD_DIAG_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
