"""局部放大诊断：把 B/C/D 的可疑区域裁出来放大，避免靠整图目测猜。"""
from pathlib import Path
from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
SHOT = HERE.parent / "background-candidates" / "rage-meter" / "rage-meter-full-meter.png"

specs = [
    ("debug-B-card-area.png", HERE / "preview-B-card-art-and-avatars.png", (180, 505, 470, 720), 2),
    ("debug-B-original-same-region.png", SHOT, (180, 505, 470, 720), 2),
    ("debug-B-difference.png", None, (180, 505, 470, 720), 2),
    ("debug-C-card-thumbnail.png", HERE / "preview-C-character-profile.png", (500, 150, 1220, 520), 1),
    ("debug-D-title-row.png", HERE / "preview-D-part-size-samples.png", (30, 140, 1250, 235), 2),
]

with Image.open(HERE / "preview-B-card-art-and-avatars.png") as b:
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
