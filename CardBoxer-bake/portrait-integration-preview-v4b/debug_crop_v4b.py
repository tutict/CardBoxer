"""V4b 接入预览的局部放大与差异诊断：看图抓到的斜线到底是什么。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
SHOT = BAKE / "background-candidates" / "rage-meter" / "rage-meter-full-meter.png"

REGIONS = {
    "A-战斗区": ("preview-A-arena-replacement.png", (280, 240, 1000, 560)),
    "A-左人": ("preview-A-arena-replacement.png", (300, 260, 580, 540)),
    "A-右人": ("preview-A-arena-replacement.png", (700, 260, 980, 540)),
    "B-卡牌区": ("preview-B-card-art-and-avatars.png", (220, 530, 1060, 710)),
    "B-头像": ("preview-B-card-art-and-avatars.png", (0, 0, 90, 60)),
    "D-头像行": ("preview-D-part-size-samples.png", (40, 140, 560, 320)),
    "C-信息表": ("preview-C-character-profile.png", (520, 500, 1240, 700)),
}

with Image.open(SHOT) as s:
    shot = s.convert("RGB")

for name, (fn, box) in REGIONS.items():
    with Image.open(HERE / fn) as f:
        im = f.convert("RGB")
    crop = im.crop(box)
    crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS).save(
        HERE / f"debug-{name}.png")
    if fn.startswith("预览-A"):
        d = ImageChops.difference(im, shot).crop(box)
        ImageEnhance.Brightness(d).enhance(4.0).resize(
            (d.width * 2, d.height * 2), Image.LANCZOS).save(
            HERE / f"debug-{name}-差异.png")
    print("CROP", name, fn, box)

# 原截帧同区域，用来确认斜线在合成前是否存在
orig = shot.crop(REGIONS["A-战斗区"][1])
orig.resize((orig.width * 2, orig.height * 2), Image.LANCZOS).save(
    HERE / "debug-A-original-capture.png")
print("DEBUG_OK")
