"""55° 侧视立绘的可复算资产量测：alpha 包围盒、逐行跨度、带坐标网格的标注图。

为什么要这一步：puppet 的分区是「每个像素归到最近的 A-pose 骨段」，
关节点靠目测写死会让分区错位并在动作帧上撕出手臂。正面版
apose_joints.json 的 11 点是按 -front.png 量的，55° 侧视投影后
x 被压缩、前后肢体重叠，必须重新量。

运行：<venv>/python.exe probe_side_assets.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
OUT = HERE / "side_assets.json"
SOURCES = {
    "player": BAKE / "3D模型探针V4b" / "v4b-angle55.png",
    "foe": BAKE / "对手怪Blender建模V1" / "foe-angle55.png",
}


def font(size):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_GRID = font(12)


def row_spans(alpha, y, threshold=16):
    w = alpha.width
    px = alpha.crop((0, y, w, y + 1)).tobytes()
    xs = [x for x, v in enumerate(px) if v > threshold]
    return (min(xs), max(xs), len(xs)) if xs else None


def grid_overlay(src: Image.Image, tag: str) -> Image.Image:
    bg = Image.new("RGBA", src.size, (232, 236, 244, 255))
    im = Image.alpha_composite(bg, src).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    for v in range(0, 768, 50):
        major = v % 100 == 0
        col = (70, 96, 160, 90 if major else 42)
        d.line((v, 0, v, 768), fill=col, width=1)
        d.line((0, v, 768, v), fill=col, width=1)
        if major:
            d.text((v + 3, 3), str(v), font=F_GRID, fill=(40, 60, 110, 220))
            d.text((3, v + 2), str(v), font=F_GRID, fill=(40, 60, 110, 220))
    d.rectangle((0, 0, 767, 767), outline=(30, 50, 100, 160), width=2)
    return im


def main() -> int:
    report = {"sources": {}, "row_spans": {}}
    for tag, path in SOURCES.items():
        assert path.is_file(), f"missing {path}"
        src = Image.open(path).convert("RGBA")
        alpha = src.getchannel("A")
        bbox = alpha.getbbox()
        extrema = alpha.getextrema()
        spans = {}
        for y in range(60, 720, 30):
            s = row_spans(alpha, y)
            if s:
                spans[str(y)] = list(s)
        info = {
            "path": str(path.relative_to(BAKE)).replace("\\", "/"),
            "size": list(src.size), "mode": src.mode,
            "alpha_bbox": list(bbox), "alpha_extrema": list(extrema),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        report["sources"][tag] = info
        report["row_spans"][tag] = spans
        grid = grid_overlay(src, tag)
        grid.save(HERE / f"资产量测-{tag}.png")
        print(f"[{tag}] {path.name} size={src.size} bbox={bbox} "
              f"alpha={extrema} bytes={info['bytes']}", flush=True)
        for y in (120, 180, 240, 300, 360, 420, 480, 540, 600, 660):
            print(f"    y={y}: {spans.get(str(y))}", flush=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("SIDE_ASSETS_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
