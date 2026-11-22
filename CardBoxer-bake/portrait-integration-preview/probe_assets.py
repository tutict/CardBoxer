"""只读探针：确认合成素材的尺寸 / alpha / 人物包围盒。

不写任何图片，不改变游戏源码。输出写进 probe_assets.txt 由外层读。
"""
from pathlib import Path
from PIL import Image

BAKE = Path(__file__).resolve().parent.parent
V3 = BAKE / "3d-model-probe-v3"
SHOT = BAKE / "background-candidates"

TARGETS = [
    V3 / "zzz-front.png",
    V3 / "zzz-angle25.png",
    V3 / "zzz-angle55.png",
    V3 / "zzz-back35.png",
    V3 / "portrait-front.png",
    V3 / "portrait-angle25.png",
    V3 / "artifact_02.png",
    SHOT / "rage-meter" / "rage-meter-full-meter.png",
    SHOT / "three-round-match" / "three-round-match-turn-1.png",
    SHOT / "integrated-engine-capture.png",
]


def alpha_bbox(im: Image.Image, threshold: int = 8):
    if "A" not in im.getbands():
        return None
    a = im.getchannel("A").point(lambda v: 255 if v > threshold else 0)
    return a.getbbox()


def describe(p: Path):
    if not p.exists():
        return f"MISSING {p}"
    with Image.open(p) as src:
        im = src.convert("RGBA")
    w, h = im.size
    corners = [im.getpixel(pt) for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]]
    bb = alpha_bbox(im)
    lines = [
        f"FILE {p.relative_to(BAKE)}",
        f"  mode={Image.open(p).mode} size={w}x{h}",
        f"  corners={corners}",
        f"  alpha_bbox(>8)={bb}",
    ]
    if bb:
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        lines.append(f"  subject={bw}x{bh}  height_ratio={bh / h:.4f}  center_x={(bb[0] + bb[2]) / 2:.1f}")
        a = im.getchannel("A")
        lines.append(f"  alpha_extremes={a.getextrema()}")
    return "\n".join(lines)


def main():
    out = []
    for t in TARGETS:
        out.append(describe(t))
    text = "\n".join(out) + "\n"
    (Path(__file__).resolve().parent / "probe_assets.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
