"""局部放大诊断：把 B/C/D 的可疑区域裁出来放大，避免靠整图目测猜。"""
from pathlib import Path
from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
SHOT = HERE.parent / "背景图候选" / "怒火槽" / "怒火槽-满槽.png"

specs = [
    ("debug-B-卡牌区.png", HERE / "预览-B-卡牌插画与头像.png", (180, 505, 470, 720), 2),
    ("debug-B-原截帧同区.png", SHOT, (180, 505, 470, 720), 2),
    ("debug-B-差异.png", None, (180, 505, 470, 720), 2),
    ("debug-C-缩略卡.png", HERE / "预览-C-角色档案板.png", (500, 150, 1220, 520), 1),
    ("debug-D-标题行.png", HERE / "预览-D-部件尺寸样张.png", (30, 140, 1250, 235), 2),
]

with Image.open(HERE / "预览-B-卡牌插画与头像.png") as b:
    bimg = b.convert("RGB")
with Image.open(SHOT) as s:
    simg = s.convert("RGB")

for name, src, box, scale in specs:
    if src is None:
        d = ImageChops.difference(bimg.crop(box), simg.crop(box))
        im = d.point(lambda v: min(255, v * 4))
    else:
        with Image.open(src) as f:
            im = f.convert("RGB").crop(box)
    im = im.resize((im.width * scale, im.height * scale), Image.Resampling.NEAREST)
    im.save(HERE / name)
    print(name, im.size)
