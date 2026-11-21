"""V4b 接入预览的局部放大与差异诊断：看图抓到的斜线到底是什么。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
SHOT = BAKE / "背景图候选" / "怒火槽" / "怒火槽-满槽.png"

REGIONS = {
    "A-战斗区": ("预览-A-战斗区替换.png", (280, 240, 1000, 560)),
    "A-左人": ("预览-A-战斗区替换.png", (300, 260, 580, 540)),
    "A-右人": ("预览-A-战斗区替换.png", (700, 260, 980, 540)),
    "B-卡牌区": ("预览-B-卡牌插画与头像.png", (220, 530, 1060, 710)),
    "B-头像": ("预览-B-卡牌插画与头像.png", (0, 0, 90, 60)),
    "D-头像行": ("预览-D-部件尺寸样张.png", (40, 140, 560, 320)),
    "C-信息表": ("预览-C-角色档案板.png", (520, 500, 1240, 700)),
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
    HERE / "debug-A-原截帧.png")
print("DEBUG_OK")
