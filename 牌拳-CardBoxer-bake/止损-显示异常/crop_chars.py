"""把回滚后 3D 帧的角色区域裁出来放大，便于判断朝向与部件重叠。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "shots" / "after-3d" / "display-live.png"
OUT = HERE / "shots" / "crops"
REGIONS = {
    "both": ((180, 230, 1100, 590), 2),
    "player": ((240, 250, 610, 580), 3),
    "foe": ((660, 250, 1030, 580), 3),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    im = Image.open(SRC).convert("RGB")
    assert im.size == (1280, 720), im.size
    for name, (box, factor) in REGIONS.items():
        c = im.crop(box)
        c = c.resize((c.width * factor, c.height * factor), Image.LANCZOS)
        p = OUT / f"crop-{name}.png"
        c.save(p)
        print("WROTE", p.name, c.size, p.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
