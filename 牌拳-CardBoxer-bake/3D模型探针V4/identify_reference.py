"""确认工程师贴的截图对应 V3 哪一份产物。

不猜：把每张候选图合成到白底、缩放到贴图尺寸，算平均绝对差，取最小者。
"""
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
V3 = BAKE / "3D模型探针V3"
CLIP = Path(r"C:\Users\tutic\.workbuddy\clipboard-images\clipboard-2026-11-07T08-20-33-060Z-2a2e87f1.png")

CANDIDATES = [
    V3 / "artifact_02.png",
    V3 / "zzz-front.png",
    V3 / "zzz-angle25.png",
    V3 / "立绘-front.png",
    V3 / "立绘-angle25.png",
    V3 / "ZZZ-四视角.png",
    V3 / "造型三版对照.png",
]


def on_white(p: Path, size):
    with Image.open(p) as f:
        im = f.convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize(size, Image.Resampling.LANCZOS)


def main():
    with Image.open(CLIP) as f:
        clip = f.convert("RGB")
    lines = [f"CLIP {CLIP.name} size={clip.size} mode={Image.open(CLIP).mode}"]
    scored = []
    for p in CANDIDATES:
        if not p.exists():
            lines.append(f"MISSING {p.name}")
            continue
        with Image.open(p) as f:
            lines.append(f"CAND {p.name} size={f.size} mode={f.mode}")
        cand = on_white(p, clip.size)
        d = ImageChops.difference(clip, cand)
        mad = sum(ImageStat.Stat(d).mean) / 3
        scored.append((mad, p.name))
    lines.append("--- mean_abs_diff (lower = closer) ---")
    for mad, name in sorted(scored):
        lines.append(f"{mad:8.3f}  {name}")
    if scored:
        lines.append(f"BEST_MATCH {min(scored)[1]}")
    text = "\n".join(lines) + "\n"
    (HERE / "identify_reference.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
